import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import shellcmd  # noqa: E402


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, env=shellcmd.scrubbed_env())


@pytest.fixture
def repo(tmp_path):
    origin, work = str(tmp_path / "origin.git"), str(tmp_path / "work")
    sh("git", "init", "-q", "--bare", "-b", "main", origin)
    sh("git", "clone", "-q", origin, work)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "c", cwd=work)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=work)
    return work


def test_git_ok_contract(repo):
    assert shellcmd.git(["rev-parse", "--verify", "--quiet", "nope"], ok=(0, 1), cwd=repo).returncode == 1
    with pytest.raises(shellcmd.CmdError, match="rev-parse"):
        shellcmd.git(["rev-parse", "--verify", "--quiet", "nope"], cwd=repo)


def test_git_missing_binary_and_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(shellcmd.CmdError):
        shellcmd.git(["status"])
    (tmp_path / "git").write_text("#!/bin/sh\nexec /bin/sleep 5\n")
    (tmp_path / "git").chmod(0o755)
    with pytest.raises(shellcmd.CmdError, match="timed out"):
        shellcmd.git(["status"], timeout=0.2)


def test_leaked_git_dir_is_scrubbed(repo, tmp_path, monkeypatch):
    other = str(tmp_path / "other")
    sh("git", "init", "-q", other)
    monkeypatch.setenv("GIT_DIR", os.path.join(other, ".git"))
    assert "GIT_DIR" not in shellcmd.scrubbed_env()
    top = shellcmd.git(["-C", repo, "rev-parse", "--show-toplevel"]).stdout.strip()
    assert os.path.realpath(top) == os.path.realpath(repo)


def test_scratch_worktree_removed_on_exception(repo, tmp_path):
    wt = str(tmp_path / "wt")
    with pytest.raises(RuntimeError):
        with shellcmd.scratch_worktree(repo, "origin/main", wt) as p:
            assert os.path.isdir(p)
            raise RuntimeError("boom")
    assert not os.path.exists(wt)
    assert wt not in shellcmd.git(["-C", repo, "worktree", "list"]).stdout


def test_scratch_worktree_bad_rev_raises(repo, tmp_path):
    with pytest.raises(shellcmd.CmdError):
        with shellcmd.scratch_worktree(repo, "origin/nope", str(tmp_path / "wt")):
            pass


def test_default_branch_refuses_when_unset_then_reads(repo):
    sh("git", "remote", "set-head", "origin", "-d", cwd=repo)
    with pytest.raises(shellcmd.CmdError, match="git remote set-head"):
        shellcmd.default_branch(repo)
    sh("git", "remote", "set-head", "origin", "main", cwd=repo)
    assert shellcmd.default_branch(repo) == "origin/main"


@pytest.mark.parametrize("url,slug", [
    ("https://github.com/caneff/agent-skills.git", "caneff/agent-skills"),
    ("git@github.com:caneff/a.b.git", "caneff/a.b"),
    ("https://github.com/caneff/a.b", "caneff/a.b"),
    ("https://example.com/x/y.git", None),
])
def test_origin_slug(repo, url, slug):
    sh("git", "remote", "set-url", "origin", url, cwd=repo)
    assert shellcmd.origin_slug(repo) == slug


def fake_herdr(tmp_path, monkeypatch, script):
    (tmp_path / "herdr").write_text("#!/bin/sh\n" + script)
    (tmp_path / "herdr").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")


def test_herdr_agent(tmp_path, monkeypatch):
    fake_herdr(tmp_path, monkeypatch, """echo '{"result":{"agent":{"agent_status":"idle"}}}'""")
    assert shellcmd.herdr_agent("w") == {"agent_status": "idle"}
    fake_herdr(tmp_path, monkeypatch, """echo '{"error":{"code":"agent_not_found"}}' >&2; exit 1""")
    assert shellcmd.herdr_agent("w") is None
    fake_herdr(tmp_path, monkeypatch, "echo down >&2; exit 1")
    with pytest.raises(shellcmd.CmdError, match="down"):
        shellcmd.herdr_agent("w")
    fake_herdr(tmp_path, monkeypatch, "exec /bin/sleep 5")
    with pytest.raises(shellcmd.CmdError, match="timed out"):
        shellcmd.herdr_agent("w", timeout=0.2)
