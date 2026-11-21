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
    if len(argv) >= 3 and argv[1] == "count" and len(argv) == 3:
        old = os.fsencode(argv[2])
        if not old:
            print("witness_replace: empty <old>", file=sys.stderr)
            return 2
        print(occurrences(sys.stdin.buffer.read(), old))
        return 0
    if len(argv) == 5 and argv[1] == "apply":
        path, old, new = argv[2], os.fsencode(argv[3]), os.fsencode(argv[4])
        if not old:
            print("witness_replace: empty <old>", file=sys.stderr)
            return 2
        with open(path, "rb") as f:
            text = f.read()
        n = occurrences(text, old)
        if n != 1:
            print(f"witness_replace: <old> occurs {n} times in {path}, not once", file=sys.stderr)
            return 1
        with open(path, "wb") as f:
            f.write(text.replace(old, new, 1))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
