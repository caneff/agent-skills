#!/usr/bin/env python3
"""Measure every adjacent fix in a dispositions sidecar against the mechanical
parts of implement's adjacent-fix rule (#1025; SKILL.md § 6 runs it).

    check_adjacent.py --repo <worktree> --base <fixed point> <dispositions-<n>.jsonl>

For each line with `"scope": "adjacent"`, its `sha` must name one commit on
the branch that touches exactly one file, a file the diff from `--base` had
already changed before that commit, with under 20 changed lines (insertions
plus deletions, as `git show --numstat` counts them). One line per adjacent
fix: `<id>: ok ...` or `BREACH <id>: <why>`. Exit 0 with no breach, 1 with
any, 2 on a usage error, an empty sidecar or a repo git cannot read. The
other two parts of the rule — one function, no public seam — take a
reading, not a count, and stay the verifier's.

An unreadable line is a breach, not a skip: it may be the adjacent line, and
an absent answer read as a clean one is the shape this check exists to stop.
"""
import argparse
import json
import subprocess
import sys

BUDGET = 20  # changed lines, the fix's test included; the fix must be under it


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def measure(repo, base, sha):
    """(kept, message) for one adjacent fix's sha: the measurement when it
    keeps the rule, the breach when it does not."""
    if not (isinstance(sha, str) and sha):
        return False, "no sha to measure"
    full = git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if full.returncode != 0:
        return False, f"sha {sha} does not resolve to a commit"
    full = full.stdout.strip()
    if git(repo, "merge-base", "--is-ancestor", full, "HEAD").returncode != 0:
        return False, f"sha {sha} is not on the branch"
    stat = git(repo, "show", "--numstat", "--format=", full)
    if stat.returncode != 0:
        return False, f"could not read {sha}: {stat.stderr.strip()}"
    rows = [r.split("\t", 2) for r in stat.stdout.splitlines() if r]
    if len(rows) != 1:
        return False, f"touches {len(rows)} files; the rule allows one"
    added, deleted, path = rows[0]
    if not (added.isdigit() and deleted.isdigit()):
        return False, f"{path} is binary; its changed lines cannot be counted"
    changed = int(added) + int(deleted)
    if changed >= BUDGET:
        return False, f"{changed} changed lines in {path}; the budget is under {BUDGET}"
    before = git(repo, "diff", "--name-only", f"{base}...{full}^")
    if before.returncode != 0:
        return False, f"could not read the diff before {sha}: {before.stderr.strip()}"
    if path not in before.stdout.splitlines():
        return False, f"{path} was not in the diff before this fix"
    return True, f"{changed} changed lines in {path}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("sidecar")
    args = ap.parse_args(argv)
    try:
        with open(args.sidecar) as fh:
            raw_lines = fh.read().splitlines()
    except OSError as e:
        print(f"check_adjacent: cannot read {args.sidecar}: {e}", file=sys.stderr)
        return 2
    # An empty sidecar is a write that failed, not a round with no fixes.
    if not any(raw.strip() for raw in raw_lines):
        print(f"check_adjacent: {args.sidecar} is empty; the verification pass wrote nothing", file=sys.stderr)
        return 2
    if git(args.repo, "rev-parse", "--git-dir").returncode != 0:
        print(f"check_adjacent: {args.repo} is not a git repository", file=sys.stderr)
        return 2

    breaches = seen = 0
    for number, raw in enumerate(raw_lines, 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = None
        if not isinstance(obj, dict):
            print(f"BREACH line {number}: not a JSON object, so it may be an unread adjacent fix")
            breaches += 1
            continue
        if "scope" not in obj:
            continue
        seen += 1
        fid = obj.get("id") or f"line {number}"
        if obj["scope"] != "adjacent":
            print(f"BREACH {fid}: unknown scope {obj['scope']!r}; the only scope is 'adjacent'")
            breaches += 1
            continue
        kept, message = measure(args.repo, args.base, obj.get("sha"))
        if kept:
            print(f"{fid}: ok, {message}")
        else:
            print(f"BREACH {fid}: {message}")
            breaches += 1
    if not seen and not breaches:
        print("no adjacent fixes in this sidecar")
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
