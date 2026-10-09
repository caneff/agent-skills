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

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "stale_refs.py")


@pytest.fixture(autouse=True)
def _no_leaked_git_env(monkeypatch):
    # A caller's leaked GIT_DIR and kin would point every fixture git call, and the
    # check itself, at the caller's repo instead of the fixture (#620).
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        monkeypatch.delenv(var, raising=False)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def write(root, files):
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)


@pytest.fixture
def repo(tmp_path):
    """A factory: a fixture repo whose `main` holds `files`, on a branch `work` cut from it."""
    def make(files):
        root = str(tmp_path / "fixture")
        os.mkdir(root)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "fixture@example.invalid")
        git(root, "config", "user.name", "fixture")
        write(root, files)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        git(root, "checkout", "-q", "-b", "work")
        return root
    return make


def commit(root, message="work"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def run(root, base="main", env=None):
    command = [sys.executable, CHECK, "--repo", root]
    if base is not None:
        command += ["--base", base]
    return subprocess.run(command, capture_output=True, text=True, env=env)


@pytest.fixture
def failing_git(tmp_path, monkeypatch):
    """A factory: an environment whose `git` fails `subcommand` and runs every other."""
    def make(subcommand):
        shim = tmp_path / "shim"
        shim.mkdir()
        with open(shim / "git", "w") as fh:
            fh.write(f'#!/bin/sh\nfor a; do [ "$a" = {subcommand} ] && {{ echo "shim: {subcommand} fails" >&2; exit 128; }}; done\n'
                     f'exec {shutil.which("git")} "$@"\n')
        os.chmod(shim / "git", 0o755)
        return {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    return make


def assert_result(result, status, present=(), absent=()):
    context = f"\n  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}"
    assert result.returncode == status, f"exit {result.returncode}, wanted {status}{context}"
    for text in present:
        assert text in result.stdout, f"stdout lacks {text!r}{context}"
    for text in absent:
        assert text not in result.stdout, f"stdout carries {text!r}{context}"


def test_renamed_path_old_spelling_remains(repo):
    root = repo({"tools/old-gate.sh": "echo gate\n",
                 "README.md": "Run tools/old-gate.sh before the PR.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    assert_result(run(root), 1,
                  present=["README.md:1:", "tools/old-gate.sh", "tools/new-gate.sh"])


def test_rename_with_every_reference_updated_is_clean(repo):
    root = repo({"tools/old-gate.sh": "echo gate\n",
                 "README.md": "Run tools/old-gate.sh before the PR.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    write(root, {"README.md": "Run tools/new-gate.sh before the PR.\n"})
    commit(root)
    result = run(root)
    assert_result(result, 0, absent=["old-gate"])


def test_unreadable_base_is_not_clean(repo):
    root = repo({"a.txt": "a\n"})
    assert_result(run(root, base="no-such-ref"), 2)


def test_deleted_file_named_by_bare_basename(repo):
    root = repo({"implement/pre-gate.sh": "echo gate\n",
                 "docs/how.md": "Then run `pre-gate.sh <sha>`.\n"})
    git(root, "rm", "-q", "implement/pre-gate.sh")
    commit(root)
    assert_result(run(root), 1,
                  present=["docs/how.md:1: pre-gate.sh (deleted)"])


def test_basename_still_tracked_elsewhere_is_not_reported(repo):
    root = repo({"a/run.sh": "echo a\n", "b/run.sh": "echo b\n",
                 "docs/how.md": "Each directory has its own run.sh.\n"})
    git(root, "rm", "-q", "a/run.sh")
    commit(root)
    assert_result(run(root), 0,
                  absent=["docs/how.md"])


def test_renamed_python_function_still_called(repo):
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n\nprint(load_cells('x'))\n"})
    write(root, {"lib.py": "def read_cells(path):\n    return path\n"})
    commit(root)
    assert_result(run(root), 1,
                  present=["tool.py:1: load_cells", "tool.py:3: load_cells"])


def test_function_moved_to_another_file_is_not_reported(repo):
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n"})
    write(root, {"lib.py": "", "cells.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from cells import load_cells\n"})
    commit(root)
    assert_result(run(root), 0, absent=["load_cells"])


def test_removed_constant_and_shell_function_still_named(repo):
    root = repo({"lib.py": "CELL_SIZE = 4\n",
                 "lib.sh": "old_helper() {\n  echo hi\n}\n",
                 "use.sh": "source lib.sh\nold_helper\n",
                 "doc.md": "Cells are CELL_SIZE wide.\n"})
    write(root, {"lib.py": "\n", "lib.sh": "\n"})
    commit(root)
    assert_result(run(root), 1,
                  present=["use.sh:2: old_helper", "doc.md:1: CELL_SIZE"])


def test_signature_change_is_not_a_removal(repo):
    root = repo({"lib.py": "def load_cells(path):\n    return path\n",
                 "tool.py": "from lib import load_cells\n"})
    write(root, {"lib.py": "def load_cells(path, strict=False):\n    return path\n"})
    commit(root)
    assert_result(run(root), 0, absent=["load_cells"])


def test_name_another_file_still_defines_is_not_reported(repo):
    root = repo({"a.py": "def shared_helper():\n    pass\n",
                 "b.py": "def shared_helper():\n    pass\n",
                 "use.py": "from b import shared_helper\n"})
    write(root, {"a.py": "\n"})
    commit(root)
    assert_result(run(root), 0, absent=["shared_helper"])


def test_removed_line_that_looks_like_a_header(repo):
    root = repo({"lib.py": "-- not a header\ndef load_cells():\n    pass\n",
                 "tool.py": "load_cells()\n"})
    write(root, {"lib.py": "\n"})
    commit(root)
    assert_result(run(root), 1,
                  present=["tool.py:1: load_cells (removed from lib.py)"])


def test_extensionless_command_name_is_not_searched_bare(repo):
    root = repo({"bin/merge-cleanup": "#!/bin/sh\n",
                 "docs/how.md": "Run merge-cleanup after the merge.\n"})
    git(root, "rm", "-q", "bin/merge-cleanup")
    commit(root)
    assert_result(run(root), 0, absent=["docs/how.md"])


def test_helper_of_a_deleted_test_file_is_not_reported(repo):
    root = repo({"gate.test.sh": "mkfixture() {\n  :\n}\n",
                 "other.test.sh": "  mkfixture\n"})
    git(root, "rm", "-q", "gate.test.sh")
    commit(root)
    assert_result(run(root), 0, absent=["mkfixture"])


def test_run_from_a_subdirectory_searches_the_whole_tree(repo):
    root = repo({"src/old.sh": "echo\n", "src/lib.py": "def load_cells():\n    pass\n",
                 "docs/a.md": "See src/old.sh and load_cells.\n"})
    git(root, "rm", "-q", "src/old.sh")
    write(root, {"src/lib.py": "\n"})
    commit(root)
    assert_result(run(os.path.join(root, "src")), 1,
                         present=["docs/a.md:1: src/old.sh (deleted)",
                                  "docs/a.md:1: load_cells (removed from src/lib.py)"])


def test_file_moved_into_a_directory_with_references_updated_is_clean(repo):
    root = repo({"gate.sh": "echo\n", "README.md": "Run gate.sh.\n"})
    git(root, "mv", "gate.sh", "tools-gate.sh")
    os.makedirs(os.path.join(root, "tools"))
    git(root, "mv", "tools-gate.sh", "tools/gate.sh")
    write(root, {"README.md": "Run tools/gate.sh.\n"})
    commit(root)
    assert_result(run(root), 0,
                         absent=["README.md"])


def test_removal_from_a_test_file_does_not_hide_the_same_removal_from_a_module(repo):
    root = repo({"a_test.py": "def load_cells():\n    pass\n",
                 "lib.py": "def load_cells():\n    pass\n", "tool.py": "load_cells()\n"})
    write(root, {"a_test.py": "\n", "lib.py": "\n"})
    commit(root)
    assert_result(run(root), 1,
                         present=["tool.py:1: load_cells (removed from lib.py)"])


def test_deleted_non_ascii_path_still_named(repo):
    root = repo({"docs/résumé.md": "x\n", "index.md": "Read docs/résumé.md.\n"})
    git(root, "rm", "-q", "docs/résumé.md")
    commit(root)
    assert_result(run(root), 1,
                         present=["index.md:1: docs/résumé.md (deleted)"])


def test_diff_noprefix_config_still_reads_removed_names(repo):
    root = repo({"lib.py": "def load_cells():\n    pass\n", "tool.py": "load_cells()\n"})
    git(root, "config", "diff.noprefix", "true")
    write(root, {"lib.py": "\n"})
    commit(root)
    assert_result(run(root), 1,
                         present=["tool.py:1: load_cells (removed from lib.py)"])


def test_removed_hyphenated_name_does_not_flag_a_longer_one(repo):
    root = repo({"lib.sh": "old-helper() {\n  :\n}\nold-helper-two() {\n  :\n}\n",
                 "use.sh": "old-helper-two\n"})
    write(root, {"lib.sh": "old-helper-two() {\n  :\n}\n"})
    commit(root)
    assert_result(run(root), 0,
                         absent=["use.sh"])


def test_uncommitted_change_is_not_a_clean_tree(repo):
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    assert_result(run(root), 2)


def test_default_base_is_origin_head(repo):
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "update-ref", "refs/remotes/origin/main", "main")
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    assert_result(run(root, base=None), 1,
                         present=["README.md:1: tools/old-gate.sh (renamed to tools/new-gate.sh)"])


def test_no_origin_head_is_not_clean(repo):
    root = repo({"a.txt": "a\n"})
    assert_result(run(root, base=None), 2)


def test_a_failing_grep_is_not_clean(repo, failing_git):
    root = repo({"tools/old-gate.sh": "echo\n", "README.md": "Run tools/old-gate.sh.\n"})
    git(root, "mv", "tools/old-gate.sh", "tools/new-gate.sh")
    commit(root)
    assert_result(run(root, env=failing_git("grep")), 2)


def test_a_failing_ls_files_is_not_clean(repo, failing_git):
    root = repo({"a.txt": "a\n"})
    assert_result(run(root, env=failing_git("ls-files")), 2)


def test_short_removed_name_is_not_searched(repo):
    root = repo({"lib.py": "def run():\n    pass\n", "doc.md": "Then run it.\n"})
    write(root, {"lib.py": "\n"})
    commit(root)
    assert_result(run(root), 0, absent=["doc.md"])


def test_deleted_basename_inside_a_longer_file_name_is_not_reported(repo):
    root = repo({"tools/gate.sh": "echo\n", "tools/pre-gate.sh": "echo\n",
                 "doc.md": "Run pre-gate.sh.\n"})
    git(root, "rm", "-q", "tools/gate.sh")
    commit(root)
    assert_result(run(root), 0, absent=["doc.md"])


def test_rename_to_a_path_of_another_length_reports_the_old_path(repo):
    root = repo({"a.sh": "echo\n", "doc.md": "Run a.sh first.\n"})
    git(root, "mv", "a.sh", "much-longer-name.sh")
    commit(root)
    assert_result(run(root), 1,
                         present=["doc.md:1: a.sh (renamed to much-longer-name.sh)"])


def test_deleted_root_file_named_with_dot_slash(repo):
    root = repo({"gate.sh": "echo\n", "doc.md": "Run ./gate.sh first.\n"})
    git(root, "rm", "-q", "gate.sh")
    commit(root)
    assert_result(run(root), 1,
                         present=["doc.md:1: gate.sh (deleted)"])


def test_name_removed_from_a_path_with_a_space(repo):
    root = repo({"my lib.py": "def load_cells():\n    pass\n", "tool.py": "load_cells()\n"})
    write(root, {"my lib.py": "\n"})
    commit(root)
    assert_result(run(root), 1,
                         present=["tool.py:1: load_cells (removed from my lib.py)"])
