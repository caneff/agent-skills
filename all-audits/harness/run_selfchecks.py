#!/usr/bin/env python3
"""Harness selfcheck runner (#556): discovers fixture-driven named checks —
one `check_*` function per behavior — in every git-tracked
`*/selfcheck_cases.py`, and runs them by name so a failure says which
behavior broke. `harness.test.sh` is the thin wrapper `tests/all.sh` globs.
"""
import importlib.util
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def discover(root=ROOT):
    out = subprocess.run(
        ["git", "ls-files", "--", "*/selfcheck_cases.py"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    return sorted(out)


def load(rel_path, root=ROOT):
    name = rel_path.replace("/", "_")[: -len(".py")]
    spec = importlib.util.spec_from_file_location(name, root / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checks_in(mod):
    return [(n, getattr(mod, n)) for n in sorted(vars(mod)) if n.startswith("check_")]


def main():
    count = 0
    for rel in discover():
        for name, fn in checks_in(load(rel)):
            label = f"{rel}::{name}"
            try:
                fn()
            except Exception:
                print(f"FAIL {label}")
                traceback.print_exc()
                sys.exit(1)
            print(f"PASS {label}")
            count += 1
    print(f"{count} checks passed")


if __name__ == "__main__":
    main()
