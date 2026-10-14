#!/usr/bin/env python3
"""Render one parallel sub-worker's brief (#1550).

    fanout-brief.py --repo <name> --worktree <path> --ticket <n> --for <worker>
                    --test-command <cmd> --assign <worker>=<file>[,<file>...] ...

`--assign` is given once per worker and states the whole split, so every
worker's brief names the same ownership map; `--for` picks the worker this
brief is for. Writes the whole prompt to
`~/.cache/agent-reviews/<repo>/fanout-<ticket>-<worker>[-<n>].md` and prints
one line naming that path: the dispatch prompt, sent to `Agent` unedited, the
way `multi-axis-code-review/render-brief.py` is. The file is created
exclusively, so a second render of the same ticket and worker takes `-2`,
`-3`, never another dispatch's file. `<repo>` goes through the ledger's
`fold_repo`, the one key every cache file uses.

The no-git-write, no-subagent and mutation rules and the report shape live in
`briefs/fanout-worker.md`, read here, never retyped.

Exit 0 and the dispatch line on stdout; 2 on a bad input, with nothing written
and nothing on stdout: a worktree that is not a directory, an empty test command, fewer than two
workers, a worker with no files, a file (or a directory holding it) owned by two workers, a `--for` worker that was not assigned, a
malformed `--assign`.
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


def render(a, owners):
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
    return "\n\n".join([
        f"# Sub-worker `{a.worker}` for #{a.ticket} in {a.repo}",
        f"You are one of {len(owners)} workers editing one shared worktree in parallel. You own the files below and nothing else.",
        f"- Worktree: {a.worktree}\n- Ticket: #{a.ticket}",
        "Your files:\n" + bullets(mine, ""),
        "## Off limits (owned by the other workers)\n" + bullets(others, ""),
        f"## Covering test\n`{a.test_command}`",
        skeleton.replace("{worktree}", a.worktree),
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
    a = p.parse_args(argv)
    a.repo = review_ledger.fold_repo(a.repo)
    a.worktree = os.path.abspath(a.worktree)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", a.repo):
        print(f"fanout-brief: repo {a.repo!r} is not a plain name", file=sys.stderr)
        return 2
    try:
        text = render(a, parse_assignments(a.assign))
        path = write_brief(text, a.repo, a.ticket, a.worker)
    except BadInput as exc:
        print(f"fanout-brief: {exc}", file=sys.stderr)
        return 2
    print(f"Read {path} and carry out the sub-worker task for #{a.ticket} it describes: that file is your whole brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
