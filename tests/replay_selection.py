#!/usr/bin/env python3
"""Replay merged PRs through today's `--changed` rules and report how many
suites each would have selected (#1955).

    tests/replay_selection.py [--prs N] [--ref origin/main]

Takes the last N squash-merged PRs on `--ref`'s first-parent line (a subject
ending `(#<n>)`), writes each one's changed paths to a temp file and asks
`tests/all.sh --list --files` what it would run, against the tree this script
is run in. Prints one line per PR (suites selected, `full` when the answer was
the whole seam) and a summary: mean, full runs, and how many ran 130 or more.
Nothing is run. Exit 2 when git or all.sh gives no answer for a PR, because a
replay that skipped a PR has not measured it.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout.decode()


def merged_prs(ref, count):
    log = git("log", "--first-parent", "--format=%H%x09%s", ref)
    prs = []
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        if re.search(r"\(#\d+\)$", subject):
            prs.append((sha, subject))
        if len(prs) == count:
            break
    return prs


def selection(paths):
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
        f.write("\n".join(paths) + "\n")
        f.flush()
        run = subprocess.run(
            ["bash", os.path.join(ROOT, "tests", "all.sh"), "--list", "--files", f.name],
            capture_output=True, text=True, cwd=ROOT,
        )
    if run.returncode != 0:
        raise RuntimeError(f"all.sh --list --files exited {run.returncode}: {run.stderr.strip()[:200]}")
    return len([l for l in run.stdout.splitlines() if l])


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prs", type=int, default=60)
    ap.add_argument("--ref", default="origin/main")
    args = ap.parse_args(argv)
    total = len(subprocess.run(["bash", os.path.join(ROOT, "tests", "all.sh"), "--list"],
                               capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines())
    counts = []
    try:
        for sha, subject in merged_prs(args.ref, args.prs):
            paths = [p for p in git("diff-tree", "-r", "--no-commit-id", "--name-only", "--no-renames", sha).splitlines() if p]
            n = selection(paths)
            counts.append(n)
            print(f"{n:4d}{' full' if n == total else '     '}  {subject[:90]}")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"replay_selection.py: {exc}", file=sys.stderr)
        return 2
    if not counts:
        print("replay_selection.py: no merged PR found on the ref; nothing was measured", file=sys.stderr)
        return 2
    print(f"{len(counts)} PRs, {total} suites: mean {sum(counts) / len(counts):.1f}; "
          f"{sum(c == total for c in counts)} full; {sum(c >= 0.85 * total for c in counts)} select 85% or more")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
