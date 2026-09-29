#!/usr/bin/env python3
"""List every place the tracked tree still spells something the branch
renamed or deleted (#1252; implement/SKILL.md § Before the PR runs it).

    stale_refs.py [--repo <worktree>] [--base <ref>]

Reads `git diff <base>...HEAD`. For each path it renamed or deleted, the old
path is searched for in the tracked tree, and so is its bare basename when no
tracked file still carries that basename (a doc names `pre-report-gate.sh`,
not its directory). For each top-level name the diff's removed lines define
(a def, class, constant or function at column 0 of a code file) that no
added line defines again and no tracked code file still defines, the name is
searched for as a whole word. One line per hit,
`<file>:<line>: <old spelling> (<what happened to it>)`. Exit 0 with no hit,
1 with any, 2 when git cannot answer: a check that could not read the diff
has not found the tree clean.
"""
import argparse
import os
import re
import subprocess
import sys


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


class GitError(Exception):
    pass


def checked(repo, *args):
    result = git(repo, *args)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def old_paths(repo, base):
    """{old path: what happened to it} for every path the diff renamed or deleted."""
    out = checked(repo, "diff", "--name-status", "-M", f"{base}...HEAD")
    gone = {}
    for row in out.splitlines():
        fields = row.split("\t")
        if fields[0].startswith("R"):
            gone[fields[1]] = f"renamed to {fields[2]}"
        elif fields[0] == "D":
            gone[fields[1]] = "deleted"
    return gone


# Top-level definitions, column 0 only: an indented def is a method or a
# nested helper, whose name is not the file's to export. Keyed by extension
# because a `def` inside a Markdown code block is prose, not a definition.
PY = [r"(?:async\s+)?def\s+(\w+)", r"class\s+(\w+)", r"([A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=(?!=)"]
SH = [r"(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)", r"function\s+([A-Za-z_][\w-]*)"]
JS = [r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)"]
RS = [r"(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|const|static|type|mod)\s+(\w+)"]
DEFINITIONS = {ext: [re.compile(p) for p in pats] for exts, pats in (
    ((".py",), PY), ((".sh", ".bash"), SH),
    ((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"), JS), ((".rs",), RS)) for ext in exts}
# A shorter name is an ordinary word (`run`, `get`), and a removed one would
# flag every sentence that uses it.
MIN_NAME = 4


def defined(path, text):
    """Names `text`, one line of `path`, defines at top level."""
    names = set()
    for pattern in DEFINITIONS.get(os.path.splitext(path)[1], ()):
        match = pattern.match(text)
        if match:
            names.add(match.group(1))
    return names


def removed_names(repo, base):
    """{name: the file it was removed from} for every top-level name the diff's
    removed lines define and its added lines do not define again."""
    out = checked(repo, "diff", "-U0", "--no-color", "-M", f"{base}...HEAD")
    minus, plus = {}, set()
    old = new = ""
    header = False  # a removed `-- comment` line inside a hunk is not a file header
    for line in out.splitlines():
        if line.startswith("diff --git "):
            header = True
        elif line.startswith("@@"):
            header = False
        elif header and line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else ""
        elif header and line.startswith("+++ "):
            new = line[6:] if line.startswith("+++ b/") else ""
        elif header:
            continue
        elif line.startswith("-"):
            for name in defined(old, line[1:]):
                minus.setdefault(name, old)
        elif line.startswith("+"):
            plus |= defined(new, line[1:])
    return {name: path for name, path in minus.items()
            if name not in plus and len(name) >= MIN_NAME}


def basename_pattern(name):
    """An extended regex for `name` standing as a whole file name: not the tail
    of a longer one (`gate.sh` inside `pre-gate.sh`), nor its stem."""
    escaped = re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", name)  # POSIX ERE's own set
    return f"(^|[^A-Za-z0-9_.-]){escaped}($|[^A-Za-z0-9_-])"


def hits(repo, *pattern):
    """(file, line, text) for each tracked line `git grep <pattern>` matches."""
    result = git(repo, "grep", "-n", "-I", *pattern)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise GitError(f"git grep {' '.join(pattern)}: {result.stderr.strip()}")
    rows = []
    for row in result.stdout.splitlines():
        path, line, text = row.split(":", 2)
        rows.append((path, line, text))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default=None)
    args = ap.parse_args(argv)
    try:
        base = args.base
        if base is None:
            base = checked(args.repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
        tracked = {os.path.basename(p) for p in checked(args.repo, "ls-files").splitlines()}
        found = 0
        for old, why in sorted(old_paths(args.repo, base).items()):
            reported = set()
            searches = [(old, ("-F", "-e", old))]
            name = os.path.basename(old)
            if name != old and name not in tracked:
                searches.append((name, ("-E", "-e", basename_pattern(name))))
            for spelling, pattern in searches:
                for path, line, _ in hits(args.repo, *pattern):
                    if (path, line) in reported:
                        continue
                    reported.add((path, line))
                    print(f"{path}:{line}: {spelling} ({why})")
                    found += 1
        for name, source in sorted(removed_names(args.repo, base).items()):
            rows = hits(args.repo, "-w", "-F", "-e", name)
            if any(name in defined(path, text) for path, _, text in rows):
                continue  # still defined somewhere: moved, not gone
            for path, line, _ in rows:
                print(f"{path}:{line}: {name} (removed from {source})")
                found += 1
    except GitError as e:
        print(f"stale_refs: {e}", file=sys.stderr)
        return 2
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
