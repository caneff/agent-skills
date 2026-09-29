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

# A caller's leaked GIT_DIR and kin would point every fixture git call, and the
# check itself, at the caller's repo instead of the fixture (#620).
for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
    os.environ.pop(var, None)

FIXTURES = []


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def clean_fixtures():
    """Remove every fixture and return the ones that would not go."""
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


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


def run(root, base="main", env=None):
    command = [sys.executable, CHECK, "--repo", root]
    if base is not None:
        command += ["--base", base]
    return subprocess.run(command, capture_output=True, text=True, env=env)


def failing_git(subcommand):
    """An environment whose `git` fails `subcommand` and runs every other."""
    shim = tempfile.mkdtemp(prefix="stale-refs-shim-")
    FIXTURES.append(shim)
    with open(os.path.join(shim, "git"), "w") as fh:
        fh.write(f'#!/bin/sh\nfor a; do [ "$a" = {subcommand} ] && {{ echo "shim: {subcommand} fails" >&2; exit 128; }}; done\n'
                 f'exec {shutil.which("git")} "$@"\n')
    os.chmod(os.path.join(shim, "git"), 0o755)
    return {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}


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


def test_run_from_a_subdirectory_searches_the_whole_tree():
    root = repo({"src/old.sh": "echo\n", "src/lib.py": "def load_cells():\n    pass\n",
                 "docs/a.md": "See src/old.sh and load_cells.\n"})
    git(root, "rm", "-q", "src/old.sh")
    write(root, {"src/lib.py": "\n"})
    commit(root)
    return assert_result("run from a subdirectory", run(os.path.join(root, "src")), 1,
                         present=["docs/a.md:1: src/old.sh (deleted)",
                                  "docs/a.md:1: load_cells (removed from src/lib.py)"])


def test_file_moved_into_a_directory_with_references_updated_is_clean():
    root = repo({"gate.sh": "echo\n", "README.md": "Run gate.sh.\n"})
    git(root, "mv", "gate.sh", "tools-gate.sh")
    os.makedirs(os.path.join(root, "tools"))
    git(root, "mv", "tools-gate.sh", "tools/gate.sh")
    write(root, {"README.md": "Run tools/gate.sh.\n"})
    commit(root)
    return assert_result("file moved into a directory, references updated", run(root), 0,
                         absent=["README.md"])


def test_removal_from_a_test_file_does_not_hide_the_same_removal_from_a_module():
    root = repo({"a_test.py": "def load_cells():\n    pass\n",
                 "lib.py": "def load_cells():\n    pass\n", "tool.py": "load_cells()\n"})
    write(root, {"a_test.py": "\n", "lib.py": "\n"})
    commit(root)
    return assert_result("same name removed from a test file and a module", run(root), 1,
                         present=["tool.py:1: load_cells (removed from lib.py)"])


def test_deleted_non_ascii_path_still_named():
    root = repo({"docs/résumé.md": "x\n", "index.md": "Read docs/résumé.md.\n"})
    git(root, "rm", "-q", "docs/résumé.md")
    commit(root)
    return assert_result("deleted non-ASCII path", run(root), 1,
                         present=["index.md:1: docs/résumé.md (deleted)"])


def test_diff_noprefix_config_still_reads_removed_names():
    root = repo({"lib.py": "def load_cells():\n    pass\n", "tool.py": "load_cells()\n"})
    git(root, "config", "diff.noprefix", "true")
    write(root, {"lib.py": "\n"})
    commit(root)
    return assert_result("diff.noprefix set", run(root), 1,
                         present=["tool.py:1: load_cells (removed from lib.py)"])


def test_removed_hyphenated_name_does_not_flag_a_longer_one():
    root = repo({"lib.sh": "old-helper() {\n  :\n}\nold-helper-two() {\n  :\n}\n",
                 "use.sh": "old-helper-two\n"})
    write(root, {"lib.sh": "old-helper-two() {\n  :\n}\n"})
    commit(root)
    return assert_result("hyphenated name inside a longer one", run(root), 0,
                         absent=["use.sh"])


def test_uncommitted_change_is_not_a_clean_tree():
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    return assert_result("uncommitted rename", run(root), 2)


def test_default_base_is_origin_head():
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "update-ref", "refs/remotes/origin/main", "main")
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    return assert_result("no --base reads origin/HEAD", run(root, base=None), 1,
                         present=["README.md:1: tools/old-gate.sh (renamed to tools/new-gate.sh)"])


def test_no_origin_head_is_not_clean():
    root = repo({"a.txt": "a\n"})
    return assert_result("no --base and no origin/HEAD", run(root, base=None), 2)


def test_a_failing_grep_is_not_clean():
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    return assert_result("git grep fails", run(root, env=failing_git("grep")), 2)


def test_a_failing_ls_files_is_not_clean():
    root = repo({"a.txt": "a\n"})
    return assert_result("git ls-files fails", run(root, env=failing_git("ls-files")), 2)


def test_short_removed_name_is_not_searched():
    root = repo({"lib.py": "def run():\n    pass\n", "doc.md": "Then run it.\n"})
    write(root, {"lib.py": "\n"})
    commit(root)
    return assert_result("removed name under four characters", run(root), 0, absent=["doc.md"])


def test_deleted_basename_inside_a_longer_file_name_is_not_reported():
    root = repo({"tools/gate.sh": "echo\n", "tools/pre-gate.sh": "echo\n",
                 "doc.md": "Run pre-gate.sh.\n"})
    git(root, "rm", "-q", "tools/gate.sh")
    commit(root)
    return assert_result("basename inside a longer file name", run(root), 0, absent=["doc.md"])


def main():
    # Every `test_` function runs: a hand-kept list lets a new case sit unrun
    # while the suite still prints PASS.
    cases = [f for name, f in globals().items() if name.startswith("test_") and callable(f)]
    failed = 0
    try:
        for case in cases:
            failed += case()
    finally:
        left = clean_fixtures()
    for root in left:
        print(f"FAIL fixture not removed: {root}")
    if failed or left:
        print(f"FAIL {failed} of {len(cases)} cases")
        return 1
    print(f"PASS {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
