#!/usr/bin/env python3
"""Render one parallel sub-worker's brief (#1550).

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

`--finding` and `--ruled` (#1620) hand a fix-round worker its task: one finding
by id, for the worker it names, listed only in that worker's brief. `--ruled`
marks a finding the controller has ruled on, flag-if-you-disagree. An id given
twice, a finding for an unassigned worker, and (once any finding is given) a
worker left with none are refused, so a finding is never dropped by a split.
The report then asks for `fixed` or `disputed` per id, and the brief caps any
test run at `--workers` workers (default 1) and `--ceiling` seconds (default
600).

The no-git-write, no-subagent and mutation rules and the report shape live in
`briefs/fanout-worker.md`, read here, never retyped.

Exit 0 and the dispatch line on stdout; 2 on a bad input, with nothing written
and nothing on stdout: a worktree that is not a directory, an empty test command, fewer than two
workers, a worker with no files, a file (or a directory holding it) owned by two workers, a `--for` worker that was not assigned, a
malformed `--assign` or `--finding`, an id given twice, a finding for a worker not
assigned, a worker with no finding when others have one.
"""
import argparse
import os
import posixpath
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "multi-axis-code-review"))
import review_ledger  # noqa: E402  (fold_repo and REVIEWS_ROOT: the one cache key)


class BadInput(Exception):
    pass


def overlaps(p, q):
    """Whether paths `p` and `q` name one file: equal, or one a directory holding the other."""
    return p == q or q.startswith(p + "/") or p.startswith(q + "/")


def parse_assignments(specs):
    """{worker: [files]} in the order given, each path normalized; refuses a malformed, empty,
    overlapping or one-worker split."""
    owners = {}
    for spec in specs:
        name, sep, rest = spec.partition("=")
        name = name.strip()
        if not sep or not name:
            raise BadInput(f"--assign {spec!r} is not <worker>=<file>[,<file>...]")
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
    if len(owners) < 2:
        raise BadInput("a fan-out needs at least two workers: pass every worker's --assign, not only this one's")
    return owners


def parse_findings(flagged, owners):
    """{worker: [(id, text, ruled)]} from `--finding`/`--ruled` specs `<worker>:<id>=<text>`.

    Empty when none were given (a brief with no task); otherwise every assigned worker needs one.
    """
    found = {w: [] for w in owners}
    seen = {}
    for ruled, specs in flagged:
        for spec in specs:
            head, sep, text = spec.partition("=")
            worker, colon, fid = head.partition(":")
            worker, fid, text = worker.strip(), fid.strip(), text.strip()
            if not (sep and colon and worker and fid and text) or not re.fullmatch(r"[A-Za-z0-9._-]+", fid):
                raise BadInput(f"finding {spec!r} is not <worker>:<id>=<text>")
            if worker not in owners:
                raise BadInput(f"finding {fid} is for {worker}, not among the assigned workers ({', '.join(owners)})")
            if fid in seen:
                raise BadInput(f"finding {fid} is given twice (for {seen[fid]} and {worker})")
            seen[fid] = worker
            found[worker].append((fid, text, ruled))
    if seen:
        for worker, items in found.items():
            if not items:
                raise BadInput(f"worker {worker} has no finding to fix: every worker in a fix round needs one")
    return found if seen else {}


def finding_bullet(fid, text, ruled):
    # Continuation lines are indented so a heading inside the text cannot become a section of the brief.
    body = text.replace("\n", "\n  ")
    return f"- `{fid}`" + (" (controller's ruling — flag if you disagree)" if ruled else "") + f": {body}"


def render(a, owners, findings=None):
    if not os.path.isdir(a.worktree):
        raise BadInput(f"worktree {a.worktree} is not a directory")
    if not a.test_command.strip():
        raise BadInput("the test command is empty")
    if a.worker not in owners:
        raise BadInput(f"--for {a.worker}: not among the assigned workers ({', '.join(owners)})")
    with open(os.path.join(HERE, "briefs", "fanout-worker.md")) as fh:
        skeleton = fh.read().strip()
    mine = owners[a.worker]
    others = [f for w, fs in owners.items() if w != a.worker for f in fs]
    bullets = lambda items, empty: "\n".join(f"- `{i}`" for i in items) or empty  # noqa: E731
    mine_findings = (findings or {}).get(a.worker, [])
    task = []
    if mine_findings:
        task = ["## Findings to fix\n" + "\n".join(finding_bullet(*f) for f in mine_findings)]
    caps = (f"## Limits\nAny solve, build or test run uses at most {a.workers} worker{'s' if a.workers != 1 else ''} "
            f"and finishes inside {a.ceiling} seconds of wall clock.")
    report = []
    if mine_findings:
        ids = ", ".join(f"`{f[0]}`" for f in mine_findings)
        report = ["## Findings report\nReport per id, one line each, for " + ids + ": `fixed` (the file and what changed) or "
                  "`disputed: <why>`. Every id gets exactly one line; a finding you did not touch is `disputed`, never omitted. "
                  "A finding marked as the controller's ruling is carried out, and your disagreement is stated on its line."]
    return "\n\n".join([
        f"# Sub-worker `{a.worker}` for #{a.ticket} in {a.repo}",
        f"You are one of {len(owners)} workers editing one shared worktree in parallel. You own the files below and nothing else.",
        f"- Worktree: {a.worktree}\n- Ticket: #{a.ticket}",
        "Your files:\n" + bullets(mine, ""),
        "## Off limits (owned by the other workers)\n" + bullets(others, ""),
        *task,
        f"## Covering test\n`{a.test_command}`",
        caps,
        skeleton.replace("{worktree}", a.worktree),
        *report,
    ]) + "\n"


def write_brief(text, repo, ticket, worker):
    """Write `text` to the review cache's `fanout-<ticket>-<worker>[-<n>].md`, never over an earlier render."""
    return review_ledger.write_cache_file(repo, f"fanout-{ticket}-{worker}", text)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
    a.repo = review_ledger.fold_repo(a.repo)
    a.worktree = os.path.abspath(a.worktree)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", a.repo):
        print(f"fanout-brief: repo {a.repo!r} is not a plain name", file=sys.stderr)
        return 2
    try:
        owners = parse_assignments(a.assign)
        if a.workers < 1 or a.ceiling < 1:
            raise BadInput("--workers and --ceiling are at least 1")
        text = render(a, owners, parse_findings([(False, a.finding), (True, a.ruled)], owners))
        path = write_brief(text, a.repo, a.ticket, a.worker)
    except BadInput as exc:
        print(f"fanout-brief: {exc}", file=sys.stderr)
        return 2
    print(f"Read {path} and carry out the sub-worker task for #{a.ticket} it describes: that file is your whole brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
