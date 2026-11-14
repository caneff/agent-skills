#!/usr/bin/env python3
"""Shared plumbing for the audit family's Python parsers.

Owns the excluded-directory set, a repo-relative source-file walk that prunes
before descending, the CLI entry (parse a captured tool output), and the six-key findings-schema row. Each audit's `audit.py`
keeps only its own parse function and imports this module via a short path
hook (see `dead-code/audit.py` for the pattern).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from procs import scrubbed_env  # noqa: E402

# The one definition of the excluded-directory set. `write_json_mirror`
# below regenerates the JSON copy `test-audit/audit.mjs` reads.
EXCLUDED_DIRS = frozenset(
    {"node_modules", "dist", "build", ".venv", "venv", "vendor", "worktrees", "mutants", ".git"}
)


JS_SUFFIXES = (".mjs", ".js")


def walk_source(root, suffix=".py", skip=None):
    """Sorted repo-relative `suffix` paths (a string or a tuple of them) under `root`, pruning
    `EXCLUDED_DIRS` and dot-dirs before descending into them.

    `skip`, when given, is a callable taking a `/`-joined relative path and
    returning True to drop it from the result — an additional per-file
    filter on top of the directory pruning above (e.g. `is_test_or_fixture`
    below, for a caller that wants only "real" source modules)."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(suffix):
                rel = os.path.relpath(os.path.join(dirpath, filename), root).replace(os.sep, "/")
                if skip is None or not skip(rel):
                    paths.append(rel)
    return sorted(paths)


# Source suffixes the Python-only audits (dead-code, type-tightness,
# docstring-coverage) name when a repo has none of their own language.
OTHER_LANGUAGES = {
    "JavaScript": (".js", ".mjs", ".cjs", ".jsx"),
    "TypeScript": (".ts", ".tsx", ".mts", ".cts"),
    "Rust": (".rs",),
    "Go": (".go",),
    "Java": (".java",),
    "Ruby": (".rb",),
    "Shell": (".sh",),
}


def _kept(rel):
    """True when no directory of `rel` is excluded or a dot-dir: `walk_source`'s
    pruning, applied to a path list."""
    return not any(d in EXCLUDED_DIRS or d.startswith(".") for d in rel.split("/")[:-1])


def tracked_source(root):
    """Sorted `root`-relative paths of the files git tracks under `root`,
    minus excluded and dot-dirs. An untracked file is no evidence of what a
    repo is written in: a stray `.py`, or the `.js` assets of an `--out`
    folder inside the repo, must not change the answer (#1751).

    `root` outside any git work tree has no tracked files to go by, so it is
    walked as a folder (`walk_source`). Any other git failure raises,
    naming git's own message."""
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True, env=scrubbed_env())
    if r.returncode != 0:
        if "not a git repository" in r.stderr:
            return walk_source(root, ("",))
        raise RuntimeError(f"git ls-files in {root} failed (exit {r.returncode}): {r.stderr.strip()}")
    return sorted(rel for rel in r.stdout.split("\0") if rel and _kept(rel))


def not_applicable(root):
    """The language a Python-only audit names when `root` holds no Python
    source but does hold another recognised language's, else None. Decided
    from `tracked_source`.

    An audit that only reads Python finds nothing on such a repo, and "nothing
    found" reads as a clean pass (defect class 1). None also covers a repo
    with no recognised source at all: with no language to name, the audit runs
    as before rather than being waved off."""
    files = tracked_source(root)
    if any(f.endswith(".py") for f in files):
        return None
    counts = {lang: sum(f.endswith(suffixes) for f in files) for lang, suffixes in OTHER_LANGUAGES.items()}
    language, count = max(counts.items(), key=lambda kv: kv[1])
    return language if count else None


def applicable_cli(root):
    """The `auditlib.py --applicable <repo>` answer, the one step 0 of every
    Python-only audit (all-audits/SKILL.md § Not applicable): print
    `applicable` and return 0, or print `not applicable: <language>` and
    return 3."""
    language = not_applicable(root)
    print(f"not applicable: {language}" if language else "applicable")
    return 3 if language else 0


def is_test_or_fixture(path):
    """True when `path` (a `/`-joined relative path) is not a worthy,
    testable source module: a test file itself (`test_*.py`, `*_test.py`,
    `*.test.mjs`/`*.test.js`), `conftest*`, `__init__.py`, not a `.py`,
    `.mjs` or `.js` file, or under an excluded or `fixtures/` directory.

    The one home for the skip rule mutation-audit's `_sibling_tests` used to
    carry by hand — pass it as `walk_source`'s `skip=` to get only "real"
    source modules, or call it directly the way `_sibling_tests` does."""
    parts = path.split("/")
    dirs, name = parts[:-1], parts[-1]
    if EXCLUDED_DIRS & set(dirs):
        return True
    if "fixtures" in dirs or "conftest" in name:
        return True
    if name == "__init__.py" or name.startswith("test_") or name.endswith("_test.py") or ".test." in name:
        return True
    if not name.endswith((".py", *JS_SUFFIXES)):
        return True
    return False


def finding(bucket, file, line, category, summary, failure="", **extra):
    """The six required findings-schema keys, plus an optional `extra` blob.

    `failure` defaults to "" — pass-one parsers name what the tool found, not
    the concrete failure a reader would hit; that's the judgment pass's job.
    """
    row = {"bucket": bucket, "file": file, "line": line, "category": category, "summary": summary, "failure": failure}
    if extra:
        row["extra"] = extra
    return row


def run_cli(argv, parse, nargs=1, usage=None):
    """The CLI entry every parser's `main()` delegates to.

    Reads `nargs` file arguments (or stdin when `nargs == 1` and none is
    given), calls `parse(*contents)`, and prints one JSON line per row.
    """
    if nargs == 1:
        text = sys.stdin.read() if len(argv) < 2 else open(argv[1], encoding="utf-8").read()
        args = (text,)
    else:
        if len(argv) < 1 + nargs:
            print(usage or f"usage: audit.py <{nargs} args>", file=sys.stderr)
            sys.exit(1)
        args = tuple(open(a, encoding="utf-8").read() for a in argv[1 : 1 + nargs])
    for row in parse(*args):
        print(json.dumps(row))


def write_json_mirror(path):
    """Write `EXCLUDED_DIRS` as a sorted JSON array — the mirror the
    `test-audit/audit.mjs` JS twin reads instead of keeping its own copy."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(EXCLUDED_DIRS), f, indent=2)
        f.write("\n")


def main(argv):
    if argv[1:2] == ["--write-json-mirror"]:
        write_json_mirror(argv[2])
        return
    if argv[1:2] == ["--applicable"] and len(argv) == 3:
        sys.exit(applicable_cli(argv[2]))
    print("usage: auditlib.py --write-json-mirror <path> | --applicable <repo>", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
