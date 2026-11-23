"""Tests for `scratch_run` against a temp repo with a bare origin and an `npm` stub on PATH; no
subprocess is patched. `HOME` and the git config are the test's own."""
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scratch_run  # noqa: E402

NPM = '#!/bin/sh\necho "npm $* in $(pwd)" >> "$NPM_LOG"\ntest -n "$NPM_RED" && exit 1\nmkdir node_modules\n'


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


def read(path):
    with open(path) as f:
        return f.read()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A clone of a bare origin with two commits on main, an `npm` stub first on PATH."""
    home = tmp_path / "home"
    write(str(home / ".gitconfig"), "[user]\n\tname = t\n\temail = t@example.test\n")
    for key, value in {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
                       "NPM_LOG": str(tmp_path / "npm.log"),
                       "PATH": str(tmp_path / "bin") + os.pathsep + os.environ["PATH"]}.items():
        monkeypatch.setenv(key, value)
    write(str(tmp_path / "bin" / "npm"), NPM, 0o755)
    root = str(tmp_path / "repo")
    git(str(tmp_path), "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(str(tmp_path), "clone", "-q", str(tmp_path / "origin.git"), root)
    commit(root, {"a.txt": "a\n"}, "a")
    commit(root, {"b.txt": "b\n"}, "b")
    return root


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(root, files, message):
    for name, text in files.items():
        write(os.path.join(root, name), text)
    git(root, "add", ".")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def worktrees(root):
    return [x for x in git(root, "worktree", "list", "--porcelain").splitlines() if x.startswith("worktree ")]


def test_the_command_runs_at_the_revision_and_its_worktree_is_gone_after(repo, tmp_path):
    log = str(tmp_path / "run.log")
    scratch_run.run_in_scratch_tree(repo, "HEAD~1", "ls; git rev-parse --show-toplevel", log, 30)
    out = read(log)
    assert "a.txt" in out and "b.txt" not in out, out
    assert "scratch-run-" in out, "the command ran in the scratch tree, not the checkout"
    assert worktrees(repo) == [f"worktree {repo}"]


def test_a_leaked_git_dir_does_not_point_the_run_at_another_repo(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_DIR", os.path.join(repo, ".git"))
    log = str(tmp_path / "run.log")
    scratch_run.run_in_scratch_tree(repo, "HEAD~1", "git log -1 --format=%s", log, 30)
    assert read(log) == "a\n", "git in the run read the checkout's HEAD (b), not the scratch tree's (a)"


def test_a_red_command_raises_naming_it_and_still_removes_the_worktree(repo, tmp_path):
    log = str(tmp_path / "run.log")
    with pytest.raises(scratch_run.ScratchError, match=r"`echo red; exit 3` failed \(output in "):
        scratch_run.run_in_scratch_tree(repo, "HEAD", "echo red; exit 3", log, 30)
    assert read(log) == "red\n"
    assert worktrees(repo) == [f"worktree {repo}"]


def test_head_is_merged_in_before_the_command(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD~1")
    git(repo, "checkout", "-q", "-b", "side", base)
    side = commit(repo, {"c.txt": "c\n"}, "c")
    log = str(tmp_path / "run.log")
    scratch_run.run_in_scratch_tree(repo, "main", "ls", log, 30, head=side)
    assert {"a.txt", "b.txt", "c.txt"} <= set(read(log).split())


def test_a_conflicting_head_raises_before_anything_runs(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD~1")
    git(repo, "checkout", "-q", "-b", "side", base)
    side = commit(repo, {"b.txt": "other\n"}, "clash")
    log = str(tmp_path / "run.log")
    with pytest.raises(scratch_run.ScratchError, match=f"merging {side} into main failed"):
        scratch_run.run_in_scratch_tree(repo, "main", "touch ran", log, 30, head=side)
    assert not os.path.exists(log)
    assert worktrees(repo) == [f"worktree {repo}"]


def test_every_tracked_lockfile_is_installed_in_its_own_directory_first(repo, tmp_path):
    commit(repo, {"package-lock.json": "{}\n", "web/package-lock.json": "{}\n", "untracked-not": "x"}, "locks")
    write(os.path.join(repo, "loose", "package-lock.json"), "{}\n")  # untracked: never installed
    log = str(tmp_path / "run.log")
    scratch_run.run_in_scratch_tree(repo, "HEAD", "test -d node_modules && test -d web/node_modules && echo ok",
                                    log, 30)
    assert read(log).strip() == "ok"
    ran = read(str(tmp_path / "npm.log")).splitlines()
    assert len(ran) == 2 and all(x.startswith("npm ci in ") for x in ran), ran
    assert ran[1].endswith("/web"), ran


def test_a_failed_install_raises_and_the_command_never_runs(repo, tmp_path, monkeypatch):
    commit(repo, {"package-lock.json": "{}\n"}, "lock")
    monkeypatch.setenv("NPM_RED", "1")
    log = str(tmp_path / "run.log")
    with pytest.raises(scratch_run.ScratchError, match=r"`npm ci` failed"):
        scratch_run.run_in_scratch_tree(repo, "HEAD", "echo ran", log, 30)
    assert "ran" not in read(log)


def test_an_npm_that_cannot_start_is_a_scratch_error_not_an_oserror(repo, tmp_path, monkeypatch):
    commit(repo, {"package-lock.json": "{}\n"}, "lock")
    lone = tmp_path / "lone"  # a PATH with git on it and no npm anywhere
    lone.mkdir()
    os.symlink(shutil.which("git"), str(lone / "git"))
    monkeypatch.setenv("PATH", str(lone))
    with pytest.raises(scratch_run.ScratchError, match=r"`npm ci` could not start"):
        scratch_run.run_in_scratch_tree(repo, "HEAD", "true", str(tmp_path / "run.log"), 30)


def test_a_revision_that_does_not_exist_is_a_scratch_error(repo, tmp_path):
    with pytest.raises(scratch_run.ScratchError, match="no-such-rev"):
        scratch_run.run_in_scratch_tree(repo, "no-such-rev", "true", str(tmp_path / "run.log"), 30)


def test_run_group_returns_the_exit_code_and_output(tmp_path):
    assert scratch_run.run_group(["sh", "-c", "echo hi; exit 4"], str(tmp_path), 10) == (4, "hi\n")


def test_run_group_kills_what_a_command_started_at_the_wall_clock(tmp_path):
    pidfile = str(tmp_path / "pid")
    with pytest.raises(scratch_run.ScratchError, match="passed the 1s wall clock"):
        scratch_run.run_group(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; sleep 30"], str(tmp_path), 1)
    pid = int(read(pidfile))
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("the command's grandchild survived the wall clock")


# `install_node_deps` and its CLI: the one install the lane's worktree creation and the scratch
# run share (#1624).
@pytest.fixture
def npm_stub(tmp_path, monkeypatch):
    """The `npm` stub first on PATH, logging to `tmp_path/npm.log`."""
    monkeypatch.setenv("NPM_LOG", str(tmp_path / "npm.log"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    write(str(tmp_path / "bin" / "npm"), NPM, 0o755)


def test_install_node_deps_installs_where_a_lockfile_sits_and_says_so(npm_stub, tmp_path):
    write(str(tmp_path / "wt" / "package-lock.json"), "{}\n")
    assert scratch_run.install_node_deps(str(tmp_path / "wt"), 30) is True
    assert os.path.isdir(tmp_path / "wt" / "node_modules")


def test_install_node_deps_without_a_lockfile_runs_no_npm(npm_stub, tmp_path):
    (tmp_path / "wt").mkdir()
    assert scratch_run.install_node_deps(str(tmp_path / "wt"), 30) is False
    assert not os.path.exists(tmp_path / "npm.log"), "npm was started in a tree with no lockfile"


def test_the_install_cli_names_the_rerun_command_and_npms_tail_on_failure(npm_stub, tmp_path):
    write(str(tmp_path / "wt" / "package-lock.json"), "{}\n")
    write(str(tmp_path / "bin" / "npm"),
          '#!/bin/sh\necho "npm $*" >> "$NPM_LOG"\nfor i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25; do echo "line $i"; done\necho boom >&2\nexit 1\n',
          0o755)
    r = subprocess.run([sys.executable, scratch_run.__file__, "install", str(tmp_path / "wt")],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"cd {tmp_path / 'wt'} && npm ci" in r.stderr
    assert "boom" in r.stderr and "line 25" in r.stderr and "line 1\n" not in r.stderr, r.stderr


def test_the_install_cli_is_silent_and_green_with_no_lockfile(npm_stub, tmp_path):
    (tmp_path / "wt").mkdir()
    r = subprocess.run([sys.executable, scratch_run.__file__, "install", str(tmp_path / "wt")],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert not os.path.exists(tmp_path / "npm.log")
