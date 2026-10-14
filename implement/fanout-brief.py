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
and nothing on stdout: a worktree that is not a directory, a worker with no
files, a file owned by two workers, a `--for` worker that was not assigned, a
malformed `--assign`.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "multi-axis-code-review"))
import review_ledger  # noqa: E402  (fold_repo and REVIEWS_ROOT: the one cache key)


class BadInput(Exception):
    pass


def parse_assignments(specs):
    """{worker: [files]} in the order given; refuses a malformed, empty or overlapping split."""
    owners, owner_of = {}, {}
    for spec in specs:
        name, sep, rest = spec.partition("=")
        name = name.strip()
        if not sep or not name:
            raise BadInput(f"--assign {spec!r} is not <worker>=<file>[,<file>...]")
        if name in owners:
            raise BadInput(f"worker {name} is assigned twice")
        files = [f.strip() for f in rest.split(",") if f.strip()]
        if not files:
            raise BadInput(f"worker {name} owns no files")
        for f in files:
            if f in owner_of:
                raise BadInput(f"{f} is owned by both {owner_of[f]} and {name}")
            owner_of[f] = name
        owners[name] = files
    return owners


def render(a, owners):
    if not os.path.isdir(a.worktree):
        raise BadInput(f"worktree {a.worktree} is not a directory")
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
        "Your files:\n" + bullets(mine, "- none"),
        "## Off limits (owned by the other workers)\n" + bullets(others, "- none: you are the only worker"),
        f"## Covering test\n`{a.test_command}`",
        skeleton,
    ]) + "\n"


def write_brief(text, repo, ticket, worker):
    """Write `text` to a file of `repo`'s (folded) review cache no earlier render holds and return its
    path. `O_EXCL` is the never-overwrite: a taken name moves on to `-2`, `-3`."""
    directory = review_ledger.REVIEWS_ROOT / repo
    directory.mkdir(parents=True, exist_ok=True)
    safe = lambda s: re.sub(r"[^A-Za-z0-9._-]", "-", s)  # noqa: E731
    stem, k = f"fanout-{safe(ticket)}-{safe(worker)}", 1
    while True:
        path = directory / (f"{stem}.md" if k == 1 else f"{stem}-{k}.md")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            k += 1
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        return path


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
