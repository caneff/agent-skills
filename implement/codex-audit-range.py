#!/usr/bin/env python3
"""Codex audit range (#1361): the merged PRs that skipped the Codex gate since the last audit,
as one diff range for a single Codex run.

    codex-audit-range.py --ledger PATH --repo R --mark SHA|DATE [--base REF]

Run from a checkout of the repo. Reads the review ledger (`docs/research/review_ledger.py`) for
PR-pass skip rows (`codex-gate`, `codex-second`, `codex-third`; never the audit's own) of repo R whose
skip reason is exactly `size` or `ceiling` (`SKILL.md` § The merge step 3), and finds each skipped
ticket's merge commit on `--base` (default `origin/HEAD`): a squash commit whose subject ends `(#<pr>)`
and either names `(#<ticket>)` earlier in the subject or has a body line closing it. A ledger row carries
no date, so "since the mark" is read off that merge commit: not an ancestor of the mark sha, or
committed after the mark date (an ISO date or date-time; one with no zone is UTC).

On stdout, oldest merge first:

    range <oldest merge's parent>..<newest merge>
    PR #<pr> ticket #<t> <reason> <merge sha>

Exit status:

  0  the range and at least one PR
  2  usage, ledger or git error
  3  no skipped PR since the mark: nothing to audit, so nothing may launch Codex

A skipped ticket with no merge commit on the base, or more than one, is named on stderr and left
out; the rest still print. When every one is left out the exit is 3, and the stdout line counts them,
since a ticket that cannot be dated is not one known to be before the mark.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docs" / "research"))
from review_ledger import CODEX_TYPES, read_ledger  # noqa: E402
from tally_review_axes import fold_repo  # noqa: E402

AUDITED_REASONS = ("size", "ceiling")
OK, ERROR, EMPTY = 0, 2, 3
_PR_SUBJECT_RE = re.compile(r"\(#(\d+)\)$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def skipped_tickets(rows: list[dict], repo: str) -> dict[int, str]:
    """{ticket: skip reason} of every Codex row of `repo` skipped for an audited reason."""
    out: dict[int, str] = {}
    for r in rows:
        if (r.get("type") in CODEX_TYPES and fold_repo(str(r.get("repo"))) == fold_repo(repo)
                and r.get("skip_reason") in AUDITED_REASONS):
            for t in r.get("tickets") or [r.get("ticket")]:
                out.setdefault(t, r["skip_reason"])
    return out


def merges(base: str) -> list[tuple[str, datetime, int, str]]:
    """(sha, commit date, PR, message) of every first-parent commit on `base` whose subject names
    a PR, oldest first."""
    found = []
    for rec in git("log", "--first-parent", "--reverse", "--format=%H%x00%cI%x00%B%x1e", base).split("\x1e"):
        if not rec.strip():
            continue
        sha, date, body = rec.strip("\n").split("\x00", 2)
        m = _PR_SUBJECT_RE.search(body.split("\n", 1)[0].strip())
        if m:
            found.append((sha, datetime.fromisoformat(date), int(m.group(1)), body))
    return found


def after_mark(mark: str):
    """A predicate on (sha, date): is this merge after the mark? A mark is a commit or a date."""
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{mark}^{{commit}}"], capture_output=True, text=True)
    if r.returncode not in (0, 1):  # not a repo, or git itself failed: no reading of the mark at all
        raise subprocess.CalledProcessError(r.returncode, r.args, stderr=r.stderr)
    sha = r.stdout.strip()
    if r.returncode == 1:
        try:
            when = datetime.fromisoformat(mark)
        except ValueError:
            raise ValueError(f"--mark {mark!r} is neither a commit nor an ISO date") from None
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        return lambda _sha, date: date > when

    def not_ancestor(merge_sha: str, _date) -> bool:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", merge_sha, sha], capture_output=True, text=True)
        if r.returncode not in (0, 1):  # an error is neither answer
            raise subprocess.CalledProcessError(r.returncode, r.args, stderr=r.stderr)
        return r.returncode == 1
    return not_ancestor


def closes(message: str, pr: int, ticket: int) -> bool:
    """Does this PR's squash commit close the ticket: `(#<ticket>)` in its subject before the PR's own,
    or a closing line in its body?"""
    subject = message.split("\n", 1)[0]
    return (pr != ticket and f"(#{ticket})" in subject) or re.search(
        rf"(?im)^\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?) #{ticket}\b", message) is not None


def pick(skipped: dict[int, str], history: list, is_after, base: str) -> tuple[list[tuple[int, str, int, int, str]], int]:
    """((position on the base, merge sha, PR, ticket, reason) of each skipped ticket merged after the
    mark, oldest first; how many were left out). A ticket closed by no merge commit, or by several,
    is named on stderr and left out."""
    picked, left_out = [], 0
    for ticket, reason in sorted(skipped.items()):
        hits = [i for i, (_, _, pr, message) in enumerate(history) if closes(message, pr, ticket)]
        if len(hits) != 1:
            print(f"codex-audit-range: ticket #{ticket} ({reason}) left out: "
                  f"{len(hits)} merge commits on {base} close it, not one", file=sys.stderr)
            left_out += 1
            continue
        sha, date, pr, _ = history[hits[0]]
        if is_after(sha, date):
            picked.append((hits[0], sha, pr, ticket, reason))
    return sorted(picked), left_out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--repo", required=True, help="the ledger's repo name, as the review cache's directory names it")
    p.add_argument("--mark", required=True, help="the last audit mark: the newest sha it covered, or its date")
    p.add_argument("--base", default="origin/HEAD", help="the default branch (default origin/HEAD)")
    args = p.parse_args(argv)
    try:
        skipped = skipped_tickets(read_ledger(args.ledger), args.repo)
        is_after = after_mark(args.mark)
        history = merges(args.base)
        picked, left_out = pick(skipped, history, is_after, args.base)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"codex-audit-range: {getattr(e, 'stderr', None) or e}".rstrip(), file=sys.stderr)
        return ERROR
    if not picked:
        undated = f"; {left_out} skipped ticket(s) left out undated, named on stderr" if left_out else ""
        print(f"no skipped PRs since the mark {args.mark}: nothing to audit{undated}")
        return EMPTY
    try:
        parent = git("rev-parse", "--verify", f"{picked[0][1]}~1").strip()
    except subprocess.CalledProcessError as e:
        print(f"codex-audit-range: the oldest merge {picked[0][1]} has no parent: {e.stderr}".rstrip(), file=sys.stderr)
        return ERROR
    print(f"range {parent}..{picked[-1][1]}")
    for _, sha, pr, ticket, reason in picked:
        print(f"PR #{pr} ticket #{ticket} {reason} {sha}")
    return OK


if __name__ == "__main__":
    sys.exit(main())
