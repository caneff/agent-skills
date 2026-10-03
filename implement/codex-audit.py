#!/usr/bin/env python3
"""Weekly Codex audit (#1362): one Codex adversarial review over the merged PRs that skipped the
merge-gate pass for size or the reserve ceiling, and the audit mark that says where the next starts.

    codex-audit.py run  [--base REF] [--ledger PATH] [--cache DIR] [--trial PATH]
                        [--dry-run [--simulate-status N] [--simulate-out FILE]]
    codex-audit.py mark --sha SHA [--date YYYY-MM-DD] [--trial PATH]

Run from a checkout of the audited repo; its name is the review cache's directory name, taken from
the common `.git` as `multi-axis-code-review/SKILL.md` does. The procedure around it, confirming and
filing the findings, is `implement/codex-audit.md`.

`run` takes these steps in order, and every one that stops the run appends one `codex-audit` ledger
row saying why, so a week with no audit is never read as a week audited clean:

  1. `codex-usage-gate.py --audit`. Capped (20) or unknown (30): stop with that status.
  2. This repo's audit mark from the trial doc (`- <repo>: <date> <sha>`), then
     `codex-audit-range.py` from it. Nothing skipped since the mark: stop with 3.
  3. The brief: each audited ticket rendered with `implement/SKILL.md`'s own jq program, then the
     controller-context appendix, as a gate pass's brief is built.
  4. The launch, from a detached worktree at the range's newest merge with `--base` its oldest
     merge's parent, between two live usage readings. Nothing is posted to the merged PRs.
  5. The record and the ledger audit row. A run that exited non-zero: stop with 4. Output the
     ledger cannot read as findings: stop with 5, and the controller reads the `.out` itself.

Exit 0 prints each finding with the audited PRs whose merge touched its file; the controller
confirms and files them, then moves the mark with `mark`. A usage, git, `gh` or ledger error is 2.
No exit but 0 is a run whose findings may be filed, and no stop moves the mark.

`--dry-run` replaces only the Codex launch: the launch step writes `--simulate-out` (default a
no-findings output) and exits `--simulate-status` (default 0), so every branch walks without
spending quota. It needs `--ledger` and `--cache` named, so a dry run never writes the real ledger.

`mark` rewrites this repo's mark line to `--sha` (default date today), refusing a sha that is not a
commit here or that does not descend from the current mark; a repo with no line gets one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "codex-usage-gate.py"
RANGE = HERE / "codex-audit-range.py"
TRIAL = HERE.parent / "docs" / "research" / "2026-09-14-codex-review-trial.md"
SKILL = HERE / "SKILL.md"
PLUGINS = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
LEDGER_CLI = HERE.parent / "docs" / "research" / "review_ledger.py"

sys.path.insert(0, str(HERE.parent / "docs" / "research"))
from review_ledger import DEFAULT_LEDGER, parse_codex_out  # noqa: E402
from tally_review_axes import REVIEWS_ROOT  # noqa: E402

OK, ERROR, EMPTY, REFUSED, UNREADABLE = 0, 2, 3, 4, 5
CAPPED, UNKNOWN = 20, 30
# The skip reason of an audit with nothing to review, one word like the gate's `size` and `ceiling`.
EMPTY_REASON = "empty"
# `implement/SKILL.md`'s ticket read, whose jq program renders a ticket and its comments; the audit
# runs that program rather than a copy of it.
_FETCH_RE = re.compile(r"--json body,comments --jq '(?P<program>.*?)'\n", re.DOTALL)
_MARK_RE = re.compile(r"^- (?P<repo>[\w.-]+): (?P<date>\d{4}-\d{2}-\d{2}) (?P<sha>[0-9a-f]{40})$", re.MULTILINE)


class Stop(Exception):
    """A step that ends the run: its exit status, and the reason its ledger skip row carries."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


def repo_name() -> str:
    top = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return Path(top).parent.name


def append_row(ledger: Path, repo: str, *args: str) -> None:
    r = subprocess.run([sys.executable, LEDGER_CLI, "append", "--repo", repo, "--type", "codex-audit",
                        "--ledger", str(ledger), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop(ERROR, f"ledger append failed: {r.stderr.strip()}")


def gate() -> None:
    r = subprocess.run([sys.executable, GATE, "--audit"], capture_output=True, text=True)
    line = r.stdout.strip()
    if r.returncode in (CAPPED, UNKNOWN):
        raise Stop(r.returncode, line)
    if r.returncode != OK:
        raise Stop(ERROR, f"usage gate exited {r.returncode}: {line or r.stderr.strip()}")


def read_mark(trial: Path, repo: str) -> str:
    """The newest sha the last audit of `repo` covered, from its line in the trial doc."""
    try:
        text = trial.read_text()
    except OSError as e:
        raise Stop(ERROR, f"trial doc {trial}: {e}") from None
    shas = [m["sha"] for m in _MARK_RE.finditer(text) if m["repo"] == repo]
    if len(shas) != 1:
        raise Stop(ERROR, f"no audit mark for {repo} in {trial}" if not shas else
                   f"{len(shas)} audit marks for {repo} in {trial}, not one")
    return shas[0]


def audit_range(ledger: Path, repo: str, mark: str, base: str) -> tuple[str, list[tuple[int, int, str, str]]]:
    """(range, [(PR, ticket, reason, merge sha)]) from `codex-audit-range.py`, oldest first."""
    r = subprocess.run([sys.executable, RANGE, "--ledger", str(ledger), "--repo", repo, "--mark", mark,
                        "--base", base], capture_output=True, text=True)
    sys.stderr.write(r.stderr)  # the tickets it left out, named
    if r.returncode == EMPTY:
        print(r.stdout.strip())
        raise Stop(EMPTY, EMPTY_REASON)
    lines = r.stdout.splitlines()
    if r.returncode != OK or not lines or not lines[0].startswith("range "):
        raise Stop(ERROR, f"codex-audit-range.py exited {r.returncode}: {r.stderr.strip() or r.stdout.strip()}")
    prs = []
    for line in lines[1:]:
        m = re.fullmatch(r"PR #(\d+) ticket #(\d+) (\S+) ([0-9a-f]{40})", line)
        if not m:
            raise Stop(ERROR, f"codex-audit-range.py printed an unreadable line: {line!r}")
        prs.append((int(m[1]), int(m[2]), m[3], m[4]))
    if not prs:
        raise Stop(ERROR, "codex-audit-range.py printed a range and no PR")
    return lines[0].removeprefix("range "), prs


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop(ERROR, f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def render_ticket(slug: str, ticket: int) -> str:
    """The ticket's body and comments, as `implement/SKILL.md` § The brief renders them."""
    programs = _FETCH_RE.findall(SKILL.read_text())
    if not programs:
        raise Stop(ERROR, f"no `--json body,comments --jq` ticket read in {SKILL}")
    r = subprocess.run(["gh", "issue", "view", str(ticket), "--repo", slug, "--json", "body,comments"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Stop(ERROR, f"gh could not read ticket #{ticket}: {r.stderr.strip()}")
    j = subprocess.run(["jq", "-r", programs[0]], input=r.stdout, capture_output=True, text=True)
    if j.returncode != 0:
        raise Stop(ERROR, f"jq could not render ticket #{ticket}: {j.stderr.strip()}")
    return j.stdout


def brief(slug: str, span: str, prs) -> str:
    """The focus text: what the range is, each audited ticket, and the controller-context appendix
    a gate pass's brief ends with (`implement/SKILL.md` § The merge step 3)."""
    listed = "".join(f"- PR #{pr} (ticket #{t}, skipped for {why}): {sha}\n" for pr, t, why, sha in prs)
    parts = [f"# Codex audit: merged PRs that skipped their own Codex pass\n\n"
             f"This is not one PR. It is the range {span} on the default branch, holding these squash "
             f"merges, each already merged with no Codex pass of its own:\n\n{listed}\n"
             f"The range also holds merges that had their own pass; judge those only where a listed PR's "
             f"change meets them. Each listed ticket follows, rendered as its own gate pass would read it.\n"]
    parts += [f"\n## PR #{pr}: ticket #{t}\n\n{render_ticket(slug, t)}" for pr, t, _, _ in prs]
    parts.append("\n## Controller context — written by the controller, not part of the ticket\n\n"
                 "**Open sibling branches.** None: every PR in this range is merged to the default branch, "
                 "and nothing in it is split onto an open branch.\n\n"
                 "**Posture.** The code under review is live in the tree; its posture is what the tree implies.\n")
    return "".join(parts)


def github_slug() -> str:
    url = git("remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise Stop(ERROR, f"origin {url} is not a GitHub repo")
    return m[1]


def usage_percent() -> str:
    """A live usage reading, `<percent> <resetsAt>` or `unknown`, as a pass record holds it."""
    return subprocess.run([sys.executable, GATE, "--percent"], capture_output=True, text=True).stdout.strip() or "unknown"


def companion() -> Path:
    try:
        root = json.loads(PLUGINS.read_text())["plugins"]["codex@openai-codex"][0]["installPath"]
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        raise Stop(ERROR, f"no codex@openai-codex plugin in {PLUGINS}: {e}") from None
    return Path(root) / "scripts" / "codex-companion.mjs"


def launch(args, span: str, body: Path, out: Path) -> int:
    """Run Codex over `span` from a detached worktree at its newest merge; its exit status."""
    base, newest = span.split("..")
    script = None if args.dry_run else companion()
    tree = out.with_name(out.stem + "-tree")
    git("worktree", "add", "--detach", str(tree), newest)
    try:
        if script is None:
            out.write_text(args.simulate_out.read_text() if args.simulate_out else
                           "No material findings (dry run: Codex was not launched).\n")
            return args.simulate_status
        with out.open("w") as f:
            return subprocess.run(["node", str(script), "adversarial-review", "--wait", "--base", base, "--",
                                   body.read_text()], cwd=tree, stdout=f, stderr=subprocess.STDOUT).returncode
    finally:
        git("worktree", "remove", "--force", str(tree))


def touched_by(prs) -> dict[int, set[str]]:
    return {pr: set(git("show", "--name-only", "--format=", sha).split()) for pr, _, _, sha in prs}


def report(findings: list[dict], prs) -> None:
    files = touched_by(prs)
    for k, f in enumerate(findings, 1):
        hits = [f"PR #{pr} ticket #{t}" for pr, t, _, _ in prs
                if f["file"] and any(p == f["file"] or p.endswith("/" + f["file"]) for p in files[pr])]
        where = ", ".join(hits) or f"no audited PR touched {f['file'] or 'a named file'}"
        print(f"finding {k} [{f['severity']}] {f['title']} ({f['file']}) — {where}")


def cmd_run(args) -> int:
    if args.dry_run and (args.ledger is None or args.cache is None):
        print("codex-audit: --dry-run needs --ledger and --cache named", file=sys.stderr)
        return ERROR
    repo = repo_name()
    ledger = args.ledger or DEFAULT_LEDGER
    try:
        gate()
        span, prs = audit_range(ledger, repo, read_mark(args.trial or TRIAL, repo), args.base)
        print(f"audit range {span}: {', '.join(f'PR #{pr}' for pr, _, _, _ in prs)}")
        cache = args.cache or REVIEWS_ROOT / repo
        cache.mkdir(parents=True, exist_ok=True)
        stem = cache / f"codex-audit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        body = stem.with_name(stem.name + "-brief.md")
        body.write_text(brief(github_slug(), span, prs))
        out, record = stem.with_suffix(".out"), stem.with_suffix(".json")
        usage_before, started = usage_percent(), datetime.now(timezone.utc).isoformat()
        status = launch(args, span, body, out)
    except Stop as stop:
        return stopped(stop, ledger, repo)
    # Codex ran: from here a failure is never recorded as an audit not launched.
    record.write_text(json.dumps({
        "prs": [pr for pr, _, _, _ in prs], "range": span, "status": status,
        "launch_sha": span.split("..")[1], "body_sha256": hashlib.sha256(body.read_bytes()).hexdigest(),
        "started": started, "completed": datetime.now(timezone.utc).isoformat(),
        "usage_before": usage_before, "usage_after": usage_percent(), "dry_run": args.dry_run}) + "\n")
    try:
        append_row(ledger, repo, "--record", str(record))
    except Stop as failed:
        print(f"codex-audit: {failed.reason}; the run's record is {record} and its output {out}", file=sys.stderr)
        return ERROR
    if status != 0:
        print(f"Codex audit run refused: it exited {status}; its output is {out}")
        print("the audit mark does not move", file=sys.stderr)
        return REFUSED
    findings, why = parse_codex_out(out.read_text())
    if findings is None:
        print(f"Codex output unreadable as findings ({why}): read it yourself: {out}")
        return UNREADABLE
    if not findings:
        print(f"no material findings; output {out}")
    report(findings, prs)
    print(f"next: confirm and file each finding (implement/codex-audit.md), then "
          f"`codex-audit.py mark --sha {span.split('..')[1]}`")
    return OK


def stopped(stop: Stop, ledger: Path, repo: str) -> int:
    """End the run on `stop`: say why, and record it as an audit not launched."""
    if stop.status == ERROR:
        print(f"codex-audit: {stop.reason}", file=sys.stderr)
        if stop.reason.startswith("no audit mark for "):
            print(f"codex-audit: write it with `codex-audit.py mark --sha <the newest merge already "
                  f"reviewed>` from this checkout", file=sys.stderr)
    elif stop.status != EMPTY:
        print(stop.reason)
    try:
        append_row(ledger, repo, "--skip-reason", stop.reason)
    except Stop as failed:
        print(f"codex-audit: {failed.reason}", file=sys.stderr)
        return ERROR
    print("the audit mark does not move", file=sys.stderr)
    return stop.status


def cmd_mark(args) -> int:
    """Move this repo's audit mark to `--sha`, or add its line after the last mark line."""
    trial = args.trial or TRIAL
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise Stop(ERROR, f"--date {args.date!r} is not YYYY-MM-DD, so the next run could not read the mark")
        repo = repo_name()
        sha = git("rev-parse", "--verify", "--quiet", f"{args.sha}^{{commit}}").strip()
        text = trial.read_text()
        marks = list(_MARK_RE.finditer(text))
        if not marks:
            raise Stop(ERROR, f"no audit mark lines in {trial}, so nowhere to write one")
        mine = [m for m in marks if m["repo"] == repo]
        if len(mine) > 1:
            raise Stop(ERROR, f"{len(mine)} audit marks for {repo} in {trial}, not one")
        if mine and subprocess.run(["git", "merge-base", "--is-ancestor", mine[0]["sha"], sha]).returncode != 0:
            raise Stop(ERROR, f"{sha} does not descend from the current mark {mine[0]['sha']}")
    except Stop as stop:
        print(f"codex-audit: {stop.reason}", file=sys.stderr)
        return stop.status
    except OSError as e:
        print(f"codex-audit: trial doc {trial}: {e}", file=sys.stderr)
        return ERROR
    line = f"- {repo}: {args.date} {sha}"
    at = mine[0] if mine else marks[-1]
    text = text[:at.start()] + line + text[at.end():] if mine else text[:at.end()] + "\n" + line + text[at.end():]
    trial.write_text(text)
    print(line)
    return OK


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--base", default="origin/HEAD")
    run.add_argument("--ledger", type=Path)
    run.add_argument("--cache", type=Path)
    run.add_argument("--trial", type=Path)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--simulate-status", type=int, default=0)
    run.add_argument("--simulate-out", type=Path)
    mark = sub.add_parser("mark")
    mark.add_argument("--sha", required=True)
    mark.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    mark.add_argument("--trial", type=Path)
    args = p.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_mark(args)


if __name__ == "__main__":
    sys.exit(main())
