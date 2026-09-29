#!/usr/bin/env python3
"""Tests for the stale-reference check (#1252; implement/SKILL.md § Before the
PR runs it). Seam: the command line — a repo and a base in, one line per
stale reference and an exit status out.

Each case builds a fixture repo whose `main` holds the base state and whose
checked-out branch makes one change, then asserts on what the check prints.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "stale_refs.py")

FIXTURES = []


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def write(root, files):
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)


def repo(files):
    """A fixture repo whose `main` holds `files`, on a branch `work` cut from it."""
    root = tempfile.mkdtemp(prefix="stale-refs-fixture-")
    FIXTURES.append(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "fixture")
    write(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "work")
    return root


def commit(root, message="work"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def run(root, base="main"):
    return subprocess.run([sys.executable, CHECK, "--repo", root, "--base", base],
                          capture_output=True, text=True)


def assert_result(label, result, status, present=(), absent=()):
    problems = []
    if result.returncode != status:
        problems.append(f"exit {result.returncode}, wanted {status}")
    for text in present:
        if text not in result.stdout:
            problems.append(f"stdout lacks {text!r}")
    for text in absent:
        if text in result.stdout:
            problems.append(f"stdout carries {text!r}")
    if problems:
        print(f"FAIL {label}: {'; '.join(problems)}\n  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}")
        return 1
    print(f"ok {label}")
    return 0


def test_renamed_path_old_spelling_remains():
    root = repo({"tools/old-gate.sh": "echo gate\n",
                 "README.md": "Run tools/old-gate.sh before the PR.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    return assert_result("renamed path, old spelling remains", run(root), 1,
                  present=["README.md:1:", "tools/old-gate.sh", "tools/new-gate.sh"])


def test_rename_with_every_reference_updated_is_clean():
    root = repo({"tools/old-gate.sh": "echo gate\n",
                 "README.md": "Run tools/old-gate.sh before the PR.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    write(root, {"README.md": "Run tools/new-gate.sh before the PR.\n"})
    commit(root)
    result = run(root)
    return assert_result("rename with every reference updated", result, 0, absent=["old-gate"])


def test_unreadable_base_is_not_clean():
    root = repo({"a.txt": "a\n"})
    return assert_result("a base git cannot resolve", run(root, base="no-such-ref"), 2)


def test_deleted_file_named_by_bare_basename():
    root = repo({"implement/pre-gate.sh": "echo gate\n",
                 "docs/how.md": "Then run `pre-gate.sh <sha>`.\n"})
    git(root, "rm", "-q", "implement/pre-gate.sh")
    commit(root)
    return assert_result("deleted file named by its bare basename", run(root), 1,
                  present=["docs/how.md:1: pre-gate.sh (deleted)"])


def test_basename_still_tracked_elsewhere_is_not_reported():
    root = repo({"a/run.sh": "echo a\n", "b/run.sh": "echo b\n",
                 "docs/how.md": "Each directory has its own run.sh.\n"})
    git(root, "rm", "-q", "a/run.sh")
    commit(root)
    return assert_result("basename another tracked file still carries", run(root), 0,
                  absent=["docs/how.md"])


def test_renamed_python_function_still_called():
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n\nprint(load_cells('x'))\n"})
    write(root, {"lib.py": "def read_cells(path):\n    return path\n"})
    commit(root)
    return assert_result("renamed Python function still called", run(root), 1,
                  present=["tool.py:1: load_cells", "tool.py:3: load_cells"])


def test_function_moved_to_another_file_is_not_reported():
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n"})
    write(root, {"lib.py": "", "cells.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from cells import load_cells\n"})
    commit(root)
    return assert_result("function moved to another file", run(root), 0, absent=["load_cells"])


def test_removed_constant_and_shell_function_still_named():
    root = repo({"lib.py": "CELL_SIZE = 4\n",
                 "lib.sh": "old_helper() {\n  echo hi\n}\n",
                 "use.sh": "source lib.sh\nold_helper\n",
                 "doc.md": "Cells are CELL_SIZE wide.\n"})
    write(root, {"lib.py": "\n", "lib.sh": "\n"})
    commit(root)
    return assert_result("removed constant and shell function", run(root), 1,
                  present=["use.sh:2: old_helper", "doc.md:1: CELL_SIZE"])


def test_signature_change_is_not_a_removal():
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n"})
    write(root, {"lib.py": "def load_cells(path, strict=False):\n    return path\n"})
    commit(root)
    return assert_result("signature change keeps the name", run(root), 0, absent=["load_cells"])


def test_name_another_file_still_defines_is_not_reported():
    root = repo({"a.py": "def shared_helper():\n    pass\n",
                 "b.py": "def shared_helper():\n    pass\n",
                 "use.py": "from b import shared_helper\n"})
    write(root, {"a.py": "\n"})
    commit(root)
    return assert_result("name another file still defines", run(root), 0, absent=["shared_helper"])


def test_removed_line_that_looks_like_a_header():
    root = repo({"lib.py": "-- not a header\ndef load_cells():\n    pass\n",
                 "tool.py": "load_cells()\n"})
    write(root, {"lib.py": "\n"})
    commit(root)
    return assert_result("removed line starting '-- '", run(root), 1,
                  present=["tool.py:1: load_cells (removed from lib.py)"])


def test_extensionless_command_name_is_not_searched_bare():
    root = repo({"bin/merge-cleanup": "#!/bin/sh\n",
                 "docs/how.md": "Run merge-cleanup after the merge.\n"})
    git(root, "rm", "-q", "bin/merge-cleanup")
    commit(root)
    return assert_result("extensionless command name", run(root), 0, absent=["docs/how.md"])


def test_helper_of_a_deleted_test_file_is_not_reported():
    root = repo({"gate.test.sh": "mkfixture() {\n  :\n}\n",
                 "other.test.sh": "  mkfixture\n"})
    git(root, "rm", "-q", "gate.test.sh")
    commit(root)
    return assert_result("helper of a deleted test file", run(root), 0, absent=["mkfixture"])


CASES = [
    test_renamed_path_old_spelling_remains,
    test_rename_with_every_reference_updated_is_clean,
    test_unreadable_base_is_not_clean,
    test_deleted_file_named_by_bare_basename,
    test_basename_still_tracked_elsewhere_is_not_reported,
    test_renamed_python_function_still_called,
    test_function_moved_to_another_file_is_not_reported,
    test_removed_constant_and_shell_function_still_named,
    test_signature_change_is_not_a_removal,
    test_name_another_file_still_defines_is_not_reported,
    test_removed_line_that_looks_like_a_header,
    test_extensionless_command_name_is_not_searched_bare,
    test_helper_of_a_deleted_test_file_is_not_reported,
]


def main():
    failed = 0
    try:
        for case in CASES:
            failed += case()
    finally:
        for root in FIXTURES:
            shutil.rmtree(root, ignore_errors=True)
    if failed:
        print(f"FAIL {failed} of {len(CASES)} cases")
        return 1
    print(f"PASS {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
