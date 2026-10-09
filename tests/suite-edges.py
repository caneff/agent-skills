#!/usr/bin/env python3
"""Cross-directory edges for `tests/all.sh --changed` (#1495).

`--changed` keeps the suites under each touched top-level directory. A suite
that loads, sources or reads a file in *another* directory is impacted when
only that other directory changes, so this derives the edges and prints the
touched directories widened to every directory that depends on one of them,
transitively. Exit 0 with the word list on stdout; any other exit means the
scan failed and the caller runs the full suite.

An edge `D -> X` means a tracked `.py`, `.sh` or `.rs` file under `D/` has a
line that reaches `X/`: a `sys.path`, `..`, `parent`, `__file__`, `source` / `.`,
`pardir`, `include_str`, `importlib` or root-variable (`ROOT`, `root`) line, where `X`
appears as a path segment or a component of a path built in code (see
`PATH_SEGMENT`, `BUILT_PATH`) on that line or the two after it (a call split
over lines). The rule over-
matches by design: an extra edge only widens the run, a missing one is the
miss this exists to close.

    suite-edges.py <dir>...          touched dirs + their dependents, one line
"""
import re
import subprocess
import sys

# A directory is reached as a path segment (`X/`, or `../X"` ending a path) or as
# a quoted word that is a component of a path built in code (`"..", "X"`,
# `ROOT / "X"`). A bare quoted word alone (`"landed"`) names nothing: dictionary
# keys and prose are full of directory-like words, and each false edge widens
# every run that touches the directory. `docs/research/` names `docs`, not
# `research`, hence the delimiters before the name.
PATH_SEGMENT = r"(?:(?:^|[\s\"'(=,:])|\.\./|(?:root|ROOT|here|HERE|[})])/)%s(?:/|(?<=\.\./%s)[\"'\s])"
BUILT_PATH = r"(?:(?:[\"']\.\.[\"']|pardir)\s*,\s*[\"']%s[\"']|/\s*[\"']%s[\"']|[\"']%s[\"']\s*/)"
HINT = re.compile(r"sys\.path|pardir|\.\.|\bparent\b|__file__|include_str|importlib|\bsource\b|^\s*\.\s|ROOT|\broot\b")
SUFFIXES = (".py", ".sh", ".rs")
SPAN = 3  # a hint line and the two after it (a call split over lines)


def reaches(span, top):
    name = re.escape(top)
    return bool(re.search(PATH_SEGMENT % (name, name), span) or re.search(BUILT_PATH % (name, name, name), span))


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def edges(files):
    tops = {p.split("/", 1)[0] for p in files if "/" in p}
    found = set()
    for path in files:
        if "/" not in path or not path.endswith(SUFFIXES):
            continue
        home = path.split("/", 1)[0]
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            if not HINT.search(line):
                continue
            span = "\n".join(lines[i:i + SPAN])
            for top in tops - {home}:
                if reaches(span, top):
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
    print(" ".join(sorted(widen(argv, found))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
