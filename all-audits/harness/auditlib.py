#!/usr/bin/env python3
"""Shared plumbing for the audit family's Python parsers.

Owns the excluded-directory set, a repo-relative source-file walk that prunes
before descending, the two-mode CLI entry (parse a captured tool output /
`--selfcheck`), and the six-key findings-schema row. Each audit's `audit.py`
keeps only its own parse function and imports this module via a short path
hook (see `dead-code/audit.py` for the pattern).
"""
import json
import os
import sys

# The one definition of the excluded-directory set. `write_json_mirror`
# below regenerates the JSON copy `test-audit/audit.mjs` reads.
EXCLUDED_DIRS = frozenset(
    {"node_modules", "dist", "build", ".venv", "venv", "vendor", "worktrees", "mutants", ".git"}
)


def walk_source(root, suffix=".py"):
    """Sorted repo-relative `suffix` paths under `root`, pruning
    `EXCLUDED_DIRS` and dot-dirs before descending into them."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(suffix):
                rel = os.path.relpath(os.path.join(dirpath, filename), root)
                paths.append(rel.replace(os.sep, "/"))
    return sorted(paths)


def finding(bucket, file, line, category, summary, failure="", **extra):
    """The six required findings-schema keys, plus an optional `extra` blob.

    `failure` defaults to "" — pass-one parsers name what the tool found, not
    the concrete failure a reader would hit; that's the judgment pass's job.
    """
    row = {"bucket": bucket, "file": file, "line": line, "category": category, "summary": summary, "failure": failure}
    if extra:
        row["extra"] = extra
    return row


def run_cli(argv, selfcheck, parse, nargs=1, usage=None):
    """The two-mode CLI entry every parser's `main()` delegates to.

    `argv[1:2] == ["--selfcheck"]` runs `selfcheck()` and returns. Otherwise
    reads `nargs` file arguments (or stdin when `nargs == 1` and none is
    given), calls `parse(*contents)`, and prints one JSON line per row.
    """
    if argv[1:2] == ["--selfcheck"]:
        selfcheck()
        return
    if nargs == 1:
        text = sys.stdin.read() if len(argv) < 2 else open(argv[1], encoding="utf-8").read()
        args = (text,)
    else:
        if len(argv) < 1 + nargs:
            print(usage or f"usage: audit.py <{nargs} args> | --selfcheck", file=sys.stderr)
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


def _selfcheck():
    assert finding("cut", "a.py", 1, "x", "s")["failure"] == ""
    assert finding("cut", "a.py", 1, "x", "s", foo=1)["extra"] == {"foo": 1}

    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "vendor"))
        os.makedirs(os.path.join(tmp, "pkg"))
        open(os.path.join(tmp, "vendor", "skip.py"), "w").close()
        open(os.path.join(tmp, "pkg", "keep.py"), "w").close()
        found = walk_source(tmp)
        assert found == ["pkg/keep.py"], found
    finally:
        import shutil

        shutil.rmtree(tmp)

    mirror = os.path.join(os.path.dirname(__file__), "excluded-dirs.json")
    mirrored = set(json.load(open(mirror, encoding="utf-8")))
    assert mirrored == EXCLUDED_DIRS, (
        f"excluded-dirs.json is stale — re-run "
        f"`python3 auditlib.py --write-json-mirror excluded-dirs.json` (got {mirrored}, want {EXCLUDED_DIRS})"
    )

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if argv[1:2] == ["--write-json-mirror"]:
        write_json_mirror(argv[2])
        return
    print("usage: auditlib.py --selfcheck | --write-json-mirror <path>", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
