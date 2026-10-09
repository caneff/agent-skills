"""Names every tracked `*_test.py` that imports `unittest` (#1494, ruling 4a).

tests/all.sh runs this before any suite: pytest would collect and pass a
unittest suite, so nothing else keeps the old idiom from coming back. Each
file is read as Python, not matched line by line, so every spelling of the
import is caught: `import os, unittest`, `import unittest.mock`,
`from unittest.mock import(patch)`, an import inside a block, and
`importlib.import_module("unittest")` or `__import__("unittest")` with a
literal name.

Prints `<path>:<line>` per import and exits 1 when there is any, 0 when
there is none. A file it cannot read or parse, or a `git ls-files` that
fails, exits 2 with the reason: a check that could not read a file has not
found it clean.
"""
import ast
import subprocess
import sys

DYNAMIC = {"import_module", "__import__"}


def is_unittest(name):
    return name == "unittest" or name.startswith("unittest.")


def imports(tree):
    """The line of every import of `unittest` or a submodule in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(is_unittest(alias.name) for alias in node.names):
                yield node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and is_unittest(node.module):
                yield node.lineno
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            arg = node.args[0]
            if (name in DYNAMIC and isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str) and is_unittest(arg.value)):
                yield node.lineno


def main():
    try:
        listed = subprocess.run(["git", "ls-files", "-z", "--", "*_test.py"],
                                capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"git ls-files failed: {exc}", file=sys.stderr)
        return 2
    found = False
    for path in filter(None, listed.decode().split("\0")):
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            print(f"could not read {path}: {exc}", file=sys.stderr)
            return 2
        for line in sorted(set(imports(tree))):
            print(f"{path}:{line}")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
