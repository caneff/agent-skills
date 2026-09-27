#!/usr/bin/env python3
"""Measure every adjacent fix in a dispositions sidecar against the mechanical
parts of implement's adjacent-fix rule (#1025; SKILL.md § 6 runs it).

    check_adjacent.py --repo <worktree> --base <fixed point> <dispositions-<n>.jsonl>

For each line with `"scope": "adjacent"`, its `sha` must name one commit on
the branch that touches one file — or that file plus its own test file
(#1097, #1175) — a source file the diff from `--base` had already changed
before that commit, with under 20 changed lines total (insertions plus
deletions, as `git show --numstat` counts them, the test file's included).
One line per adjacent
fix: `<id>: ok ...` or `BREACH <id>: <why>`. Exit 0 with no breach, 1 with
any, 2 on a usage error, an empty sidecar or a repo git cannot read. The
other two parts of the rule — one function, no public seam — take a
reading, not a count, and stay the verifier's.

An unreadable line is a breach, not a skip: it may be the adjacent line, and
an absent answer read as a clean one is the shape this check exists to stop.
"""
import argparse
import json
import os
import subprocess
import sys

BUDGET = 20  # changed lines, the fix's test included; the fix must be under it


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def _test_source_stem(path):
    """If `path`'s basename looks like a test file, (dirname, source stem,
    source ext) of the file it would test; else None. Covers this repo's own
    `<stem>_test.py` convention, pytest's `test_<stem>.py`, and the
    `<stem>.test.<ext>` convention (e.g. `obs-session.test.mjs`)."""
    d, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    if not ext:
        return None
    if stem.endswith("_test") and len(stem) > len("_test"):
        return d, stem[: -len("_test")], ext
    if stem.startswith("test_") and len(stem) > len("test_"):
        return d, stem[len("test_"):], ext
    stem2, ext2 = os.path.splitext(stem)
    if ext2 == ".test" and stem2:
        return d, stem2, ext
    return None


def own_test_pair(path_a, path_b):
    """(source, test) if one of `path_a`, `path_b` is the other's own test
    file, else None. Same directory only (#1152, deciding the question
    #1097 and #1175 left open): a same-stem file in a different directory,
    such as `tests/test_runfile.py` beside a root `runfile.py`, does not
    count — it is a second file the fix reached into, not its own test."""
    for test_path, src_path in ((path_a, path_b), (path_b, path_a)):
        info = _test_source_stem(test_path)
        if info is None:
            continue
        test_dir, src_stem, src_ext = info
        src_dir, src_base = os.path.split(src_path)
        if src_dir != test_dir:
            continue
        if os.path.splitext(src_base) == (src_stem, src_ext):
            return src_path, test_path
    return None


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
    if len(rows) not in (1, 2):
        return False, f"touches {len(rows)} files; the rule allows one file plus its own test file"
    pair = None
    if len(rows) == 2:
        pair = own_test_pair(rows[0][2], rows[1][2])
        if pair is None:
            return False, f"touches {rows[0][2]} and {rows[1][2]}, which are not one file and its own test file"
    for added, deleted, path in rows:
        if not (added.isdigit() and deleted.isdigit()):
            return False, f"{path} is binary; its changed lines cannot be counted"
    changed = sum(int(added) + int(deleted) for added, deleted, _ in rows)
    paths = " and ".join(path for _, _, path in rows)
    if changed >= BUDGET:
        return False, f"{changed} changed lines in {paths}; the budget is under {BUDGET}"
    source_path = pair[0] if pair else rows[0][2]
    before = git(repo, "diff", "--name-only", f"{base}...{full}^")
    if before.returncode != 0:
        return False, f"could not read the diff before {sha}: {before.stderr.strip()}"
    if source_path not in before.stdout.splitlines():
        return False, f"{source_path} was not in the diff before this fix"
    return True, f"{changed} changed lines in {paths}"


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
