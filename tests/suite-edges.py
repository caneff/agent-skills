#!/usr/bin/env python3
"""Cross-directory edges for `tests/all.sh --changed` (#1495).

`--changed` keeps the suites under each touched top-level directory. A suite
that loads, sources or reads a file in *another* directory is impacted when
only that other directory changes, so this derives the edges and prints the
touched directories widened to every directory that depends on one of them,
transitively. Exit 0 with the word list on stdout; any other exit means the
scan failed and the caller runs the full suite.

An edge `D -> X` means a tracked `.py` or `.sh` file under `D/` has a line that
reaches `X/`: a `sys.path` line, a `..` path, a `source` / `.` line, or a line
naming a root variable (`ROOT`, `root`, `repo`, `REPO`), and in the same line
`X` appears as a path segment (`X/`) or a quoted word (`"X"`). The rule over-
matches by design: an extra edge only widens the run, a missing one is the
miss this exists to close.

    suite-edges.py <dir>...          touched dirs + their dependents, one line
    suite-edges.py --edges           every edge, `D X` per line
"""
import re
import subprocess
import sys

# What may sit just before a directory name for it to be a top-level directory
# and not the tail of another path (`docs/research/` names `docs`, not `research`).
BEFORE = r"(?:^|[\s\"'(=,:]|\.\./|(?:root|ROOT|repo|REPO|here|HERE|[})])/)"
HINT = re.compile(r"sys\.path|\.\.|\bsource\b|^\s*\.\s|ROOT|\broot\b|\brepo\b|REPO")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def edges(files):
    tops = {p.split("/", 1)[0] for p in files if "/" in p}
    found = set()
    for path in files:
        if "/" not in path or not path.endswith((".py", ".sh")):
            continue
        home = path.split("/", 1)[0]
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not HINT.search(line):
                    continue
                for top in tops - {home}:
                    if re.search(BEFORE + re.escape(top) + r"(?=/|[\"'])", line):
                        found.add((home, top))
    return found


def widen(touched, found):
    """`tests/` always runs, so it is a target only when touched itself and
    never a dependent: otherwise its own edges would chain every directory
    to every other one."""
    kept = set(touched)
    grew = True
    while grew:
        grew = False
        for home, top in found:
            if top in kept and home not in kept and home != "tests":
                kept.add(home)
                grew = True
    return kept


def main(argv):
    found = edges(tracked())
    if argv == ["--edges"]:
        for home, top in sorted(found):
            print(home, top)
        return 0
    print(" ".join(sorted(widen(argv, found))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
