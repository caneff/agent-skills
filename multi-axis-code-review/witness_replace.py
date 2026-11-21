#!/usr/bin/env python3
"""The literal string replacement behind `witness-check.sh --file --old --new` (#1708).

    witness_replace.py count <old>            reads the text on stdin, prints how many times
                                              <old> occurs in it, overlapping occurrences included
    witness_replace.py apply <path> <old> <new>
                                              replaces the one occurrence of <old> in <path>

Everything is bytes and nothing is interpreted: no regex, no escapes, no shell, no trailing
newline stripped. `apply` replaces only when <old> occurs exactly once and exits 1 otherwise, so
a witness never runs on a mutation that did not land. An empty <old> occurs everywhere, so both
commands exit 2 on it.
"""
import os
import sys


def occurrences(text: bytes, old: bytes) -> int:
    """Overlapping count: `aa` in `aaa` is two positions, and either one is ambiguous."""
    n, at = 0, text.find(old)
    while at != -1:
        n += 1
        at = text.find(old, at + 1)
    return n


def main(argv: list[str]) -> int:
    mode, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    if (mode, len(args)) not in (("count", 1), ("apply", 3)) or not os.fsencode(args[-2 if mode == "apply" else 0]):
        print(__doc__, file=sys.stderr)  # a wrong shape, or an empty <old>
        return 2
    if mode == "count":
        print(occurrences(sys.stdin.buffer.read(), os.fsencode(args[0])))
        return 0
    path, old, new = args[0], os.fsencode(args[1]), os.fsencode(args[2])
    with open(path, "rb") as f:
        text = f.read()
    n = occurrences(text, old)
    if n != 1:
        print(f"witness_replace: <old> occurs {n} times in {path}, not once", file=sys.stderr)
        return 1
    with open(path, "wb") as f:
        f.write(text.replace(old, new, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
