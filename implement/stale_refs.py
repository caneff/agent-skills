#!/usr/bin/env python3
"""List every place the tracked tree still spells something the branch
renamed or deleted (#1252; implement/SKILL.md § Before the PR runs it).

    stale_refs.py [--repo <worktree>] [--base <ref>]

Reads `git diff <base>...HEAD`, `<base>` defaulting to `origin/HEAD`, and
searches the whole tracked tree whatever directory it runs from:

- Each path the diff renamed or deleted, as a whole path. Its bare basename
  too, when that has an extension and no tracked file still carries it: a
  doc names `pre-report-gate.sh`, not its directory, while an extensionless
  name is a command, which may live on under another implementation.
- Each top-level name the diff's removed lines define (a def, class,
  constant or function at column 0 of a Python, shell, JS/TS or Rust file),
  as a whole word, unless a tracked file still defines it (it moved) or it
  is under 4 characters or came from a test file (a test's helpers are its
  own).

One line per hit, `<file>:<line>: <old spelling> (<what happened to it>)`.
Exit 0 with no hit, 1 with any, 2 when git cannot answer or the tree has
uncommitted changes: a check that could not read the diff it was meant to
read has not found the tree clean.
"""
import argparse
import os
import re
import subprocess
import sys


def git(repo, *args):
    # quotePath off: a non-ASCII path would otherwise come back octal-quoted
    # and be searched for in a spelling no file uses.
    return subprocess.run(["git", "-C", repo, "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True)


class GitError(Exception):
    pass


def checked(repo, *args):
    result = git(repo, *args)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


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


def is_test(path):
    """A test file's top-level names are its own helpers: nothing imports
    them, so another file using the same word is not a stale reference."""
    base = os.path.basename(path)
    return (base.startswith("test_") or "_test." in base or ".test." in base
            or path.startswith("tests/") or "/tests/" in path)


def defined(path, text):
    """Names `text`, one line of `path`, defines at top level."""
    names = set()
    for pattern in DEFINITIONS.get(os.path.splitext(path)[1], ()):
        match = pattern.match(text)
        if match:
            names.add(match.group(1))
    return names


def read_diff(repo, base):
    """({old path: what happened to it}, {name: the file it was removed from})
    from one read of the diff: the paths it renamed or deleted, and the
    top-level names its removed lines define outside test files."""
    # Prefixes pinned so a user's diff.noprefix cannot strip the `a/` and
    # `b/` the headers are parsed by.
    out = checked(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "-M",
                  "--src-prefix=a/", "--dst-prefix=b/", f"{base}...HEAD")
    gone, removed = {}, {}
    old = ""
    header = False  # a removed `-- comment` line inside a hunk is not a file header
    for line in out.splitlines():
        if line.startswith("diff --git "):
            header, old = True, ""
            pair = line[len("diff --git "):]
            # A deletion names one path twice, `a/<p> b/<p>`: the halves are
            # equal, so the split is exact however many spaces <p> holds.
            old = pair[2:2 + (len(pair) - 5) // 2]
        elif line.startswith("@@"):
            header = False
        elif not header:
            if line.startswith("-") and not is_test(old):
                for name in defined(old, line[1:]):
                    removed.setdefault(name, old)
        elif line.startswith("rename from "):
            old = line[len("rename from "):]
        elif line.startswith("rename to "):
            gone[old] = f"renamed to {line[len('rename to '):]}"
        elif line.startswith("deleted file mode"):
            gone[old] = "deleted"
        elif line.startswith("--- a/"):
            old = line[len("--- a/"):]
    return gone, {n: p for n, p in removed.items() if len(n) >= MIN_NAME}


def whole(spelling, before):
    """An extended regex for `spelling` not embedded in a longer name: no name
    character after it, and none of `before` ahead of it."""
    escaped = re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", spelling)  # POSIX ERE's own set
    return f"(^|[^{before}]){escaped}($|[^A-Za-z0-9_-])"


# A path stands alone when no name character or `/` precedes it (`gate.sh`
# is not `tools/gate.sh`); a basename may sit under any directory.
PATH_BEFORE, BASENAME_BEFORE, NAME_BEFORE = "A-Za-z0-9_./-", "A-Za-z0-9_.-", "A-Za-z0-9_$-"


def hits(repo, pattern):
    """(file, line, text) for each tracked line `pattern` matches."""
    result = git(repo, "grep", "-n", "-I", "-E", "-e", pattern)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise GitError(f"git grep {pattern}: {result.stderr.strip()}")
    return [tuple(row.split(":", 2)) for row in result.stdout.splitlines()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default=None)
    args = ap.parse_args(argv)
    try:
        # From the top: `git grep` searches only below its cwd, while the
        # diff names paths from the root.
        root = checked(args.repo, "rev-parse", "--show-toplevel").strip()
        base = args.base or checked(
            root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
        dirty = checked(root, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise GitError("tracked files have uncommitted changes; the diff reads HEAD, "
                           "so commit first:\n" + dirty.rstrip())
        tracked = {os.path.basename(p) for p in checked(root, "ls-files").splitlines()}
        gone, removed = read_diff(root, base)
        found = 0
        for old, why in sorted(gone.items()):
            reported = set()
            searches = [(old, whole(old, PATH_BEFORE))]
            name = os.path.basename(old)
            if name != old and os.path.splitext(name)[1] and name not in tracked:
                searches.append((name, whole(name, BASENAME_BEFORE)))
            for spelling, pattern in searches:
                for path, line, _ in hits(root, pattern):
                    if (path, line) not in reported:
                        reported.add((path, line))
                        print(f"{path}:{line}: {spelling} ({why})")
                        found += 1
        for name, source in sorted(removed.items()):
            rows = hits(root, whole(name, NAME_BEFORE))
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
