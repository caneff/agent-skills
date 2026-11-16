#!/usr/bin/env python3
"""Render one parallel sub-worker's brief.

    fanout-brief.py --repo <name> --worktree <path> --ticket <n> --for <worker>
                    --test-command <cmd> --assign <worker>=<file>[,<file>...] ...
                    [--finding <worker>:<id>=<text>]... [--ruled <worker>:<id>=<text>]...
                    [--workers <k>] [--ceiling <seconds>]

`--assign` is given once per worker and states the whole split, so every
worker's brief names the same ownership map; `--for` picks the worker this
brief is for. Writes the whole prompt to
`~/.cache/agent-reviews/<repo>/fanout-<ticket>-<worker>[-<n>].md` and prints
one line naming that path: the dispatch prompt, sent to `Agent` unedited, the
way `multi-axis-code-review/render-brief.py` is. The file is created
exclusively, so a second render of the same ticket and worker takes `-2`,
`-3`, never another dispatch's file. `<repo>` goes through the ledger's
`fold_repo`, the one key every cache file uses.

`--finding` and `--ruled` hand a fix-round worker its task: one finding by
id, for the worker it names, listed only in that worker's brief. `--ruled`
marks a finding the controller has ruled on, flag-if-you-disagree. The brief
then asks for `fixed` or `disputed` per id, in a section of its own that item 5
of the skeleton's report points to, and caps any test run at `--workers`
workers (default 1) and `--ceiling` seconds (default 600). The renderer cannot
see the review sidecars: passing every id is the caller's. What it refuses is
listed once, in `RULES` (the `--help` epilog).

The no-git-write, no-subagent and mutation rules and the report shape live in
`briefs/fanout-worker.md`, read here, never retyped; only the per-id findings
report, which depends on the findings given, is built here.

Exit 0 and the dispatch line on stdout; 2 on a bad input, with nothing written
and nothing on stdout.
"""
import argparse
import os
import posixpath
import re
import sys
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "multi-axis-code-review"))
import review_cache  # noqa: E402  (fold_repo and REVIEWS_ROOT: the one cache key)


class BadInput(Exception):
    pass


def overlaps(p, q):
    """Whether paths `p` and `q` name one file: equal, or one a directory holding the other."""
    return p == q or q.startswith(p + "/") or p.startswith(q + "/")


def parse_assignments(specs):
    """{worker: [files]} in the order given, each path normalized; refuses a malformed, empty or
    overlapping split. One worker is a valid split (a fix round with a single sub-worker)."""
    owners = {}
    for spec in specs:
        name, sep, rest = spec.partition("=")
        name = name.strip()
        if not sep or not name:
            raise BadInput(f"--assign {spec!r} is not <worker>=<file>[,<file>...]")
        if ":" in name:
            raise BadInput(f"worker name {name!r} holds ':', which --finding reads as the worker/id separator")
        if name in owners:
            raise BadInput(f"worker {name} is assigned twice")
        files = list(dict.fromkeys(posixpath.normpath(f.strip()) for f in rest.split(",") if f.strip()))
        if not files:
            raise BadInput(f"worker {name} owns no files")
        for other, theirs in owners.items():
            for f in files:
                for g in theirs:
                    if overlaps(f, g):
                        raise BadInput(f"{f} is owned by both {other} and {name}" + ("" if f == g else f" (as {g})"))
        owners[name] = files
    return owners


class Finding(NamedTuple):
    id: str
    text: str
    ruled: bool


def parse_findings(flagged, owners):
    """{worker: [Finding]} from `--finding`/`--ruled` specs `<worker>:<id>=<text>`.

    Empty when none were given (a brief with no task); otherwise every assigned worker needs one.
    """
    found = {w: [] for w in owners}
    seen = {}
    for ruled, specs in flagged:
        for spec in specs:
            head, sep, text = spec.partition("=")
            worker, colon, fid = head.partition(":")
            worker, fid, text = worker.strip(), fid.strip(), text.strip()
            if not (sep and colon and worker and fid and text):
                raise BadInput(f"finding {spec!r} is not <worker>:<id>=<text>")
            if not re.fullmatch(r"[A-Za-z0-9._-]+", fid):
                raise BadInput(f"finding id {fid!r} may hold only letters, digits, '.', '_' and '-'")
            if worker not in owners:
                raise BadInput(f"finding {fid} is for {worker}, not among the assigned workers ({', '.join(owners)})")
            if fid in seen:
                first, first_ruled = seen[fid]
                hint = (" — once with --finding and once with --ruled: pass it with one of them, not both"
                        if first_ruled != ruled else "")
                raise BadInput(f"finding {fid} is given twice (for {first} and {worker}){hint}")
            seen[fid] = (worker, ruled)
            found[worker].append(Finding(fid, text, ruled))
    if seen:
        for worker, items in found.items():
            if not items:
                raise BadInput(f"worker {worker} has no finding to fix: every worker in a fix round needs one")
    return found


# A command segment whose first word is one of these runs no test, whatever its arguments say.
NO_TEST_WORDS = {"true", "false", ":", "echo", "printf", "exit", "test", "[", "ls", "cat", "sleep", "pwd", "cd"}


def runs_no_tests(cmd):
    """A static answer, not a run: True when every segment of `cmd` (split on `&&`, `||`, `;` and
    `|`) starts, past any `VAR=value` prefix, with a no-op such as `true`, `echo` or `cd`. A runner
    that selects nothing (`pytest -k nomatch`) or a non-test command (`ruff check`) is beyond it."""
    for segment in re.split(r"&&|\|\||;|\|", cmd):
        words = [w for w in segment.split() if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", w)]
        if words and words[0] not in NO_TEST_WORDS:
            return False
    return True


def finding_bullet(f):
    # Continuation lines are indented so a heading inside the text cannot become a section of the brief.
    body = f.text.replace("\n", "\n  ")
    return f"- `{f.id}`" + (" (controller's ruling — flag if you disagree)" if f.ruled else "") + f": {body}"


def render(a, owners, findings):
    if not os.path.isdir(a.worktree):
        raise BadInput(f"worktree {a.worktree} is not a directory")
    if not a.test_command.strip():
        raise BadInput("the test command is empty")
    if runs_no_tests(a.test_command):
        raise BadInput(f"the test command {a.test_command!r} runs no tests: every command in it is a no-op "
                       f"({', '.join(sorted(NO_TEST_WORDS))})")
    if a.worker not in owners:
        raise BadInput(f"--for {a.worker}: not among the assigned workers ({', '.join(owners)})")
    with open(os.path.join(HERE, "briefs", "fanout-worker.md")) as fh:
        skeleton = fh.read().strip()
    mine = owners[a.worker]
    others = [f for w, fs in owners.items() if w != a.worker for f in fs]
    n = len(owners)
    intro = (f"You are one of {n} workers editing one shared worktree in parallel. You own the files below and nothing else."
             if n > 1 else "You are the only worker on this ticket in this worktree. You own the files below and nothing else.")
    bullets = lambda items, empty: "\n".join(f"- `{i}`" for i in items) or empty  # noqa: E731
    caps = (f"## Limits\nAny solve, build or test run uses at most {a.workers} worker{'s' if a.workers != 1 else ''} "
            f"and finishes inside {a.ceiling} seconds of wall clock.")
    mine_findings = findings.get(a.worker, [])
    task = []
    report = []
    if mine_findings:
        task = ["## Findings to fix\n" + "\n".join(finding_bullet(f) for f in mine_findings)]
        ids = ", ".join(f"`{f.id}`" for f in mine_findings)
        report = ["## Findings report\nReport per id, one line each, for " + ids + ": `fixed` (the file and what changed) or "
                  "`disputed: <why>`. Every id gets exactly one line; a finding you did not touch is `disputed`, never omitted. "
                  "A finding marked as the controller's ruling is carried out, and your disagreement is stated on its line."]
    return "\n\n".join([
        f"# Sub-worker `{a.worker}` for #{a.ticket} in {a.repo}",
        intro,
        f"- Worktree: {a.worktree}\n- Ticket: #{a.ticket}",
        "Your files:\n" + bullets(mine, ""),
        *(["## Off limits (owned by the other workers)\n" + bullets(others, "")] if others else []),
        *task,
        f"## Covering test\n`{a.test_command}`",
        caps,
        skeleton.replace("{worktree}", a.worktree).replace("{worker}", a.worker),
        *report,
    ]) + "\n"


def write_brief(text, repo, ticket, worker):
    """Write `text` to the review cache's `fanout-<ticket>-<worker>[-<n>].md`, never over an earlier render."""
    return review_cache.write_cache_file(repo, f"fanout-{ticket}-{worker}", text)


RULES = """rules (exit 2, nothing written, on any of these):
  --worktree   must be a directory. --for must be one of the assigned workers.
  --assign   one worker is valid; several must own disjoint files; a worker owns at least one.
  --finding / --ruled   an id is given once: with --finding or with --ruled, not both. A --ruled
             id needs no --finding. Once any finding is given, every worker needs at least one
             (a worker with no finding is a worker with nothing to fix: leave it out).
  --test-command   refused when empty or when every command in it is a no-op (true, echo,
             cd...); a runner that selects nothing is not caught."""


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=RULES,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--ticket", required=True)
    p.add_argument("--for", dest="worker", required=True)
    p.add_argument("--test-command", required=True)
    p.add_argument("--assign", action="append", default=[], required=True)
    p.add_argument("--finding", action="append", default=[])
    p.add_argument("--ruled", action="append", default=[])
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--ceiling", type=int, default=600)
    a = p.parse_args(argv)
    a.repo = review_cache.fold_repo(a.repo)
    a.worktree = os.path.abspath(a.worktree)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", a.repo):
        print(f"fanout-brief: repo {a.repo!r} is not a plain name", file=sys.stderr)
        return 2
    try:
        owners = parse_assignments(a.assign)
        if a.workers < 1 or a.ceiling < 1:
            raise BadInput(f"--workers ({a.workers}) and --ceiling ({a.ceiling}) must each be at least 1")
        text = render(a, owners, parse_findings([(False, a.finding), (True, a.ruled)], owners))
        path = write_brief(text, a.repo, a.ticket, a.worker)
    except BadInput as exc:
        print(f"fanout-brief: {exc}", file=sys.stderr)
        return 2
    print(f"Read {path} and carry out the sub-worker task for #{a.ticket} it describes: that file is your whole brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
