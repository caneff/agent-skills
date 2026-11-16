import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_identity  # noqa: E402


def _init(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return str(path)


def _config(repo, key):
    return subprocess.run(["git", "-C", repo, "config", "--local", key], capture_output=True, text=True).stdout.strip()


def test_configure_writes_the_fixture_identity_inside_the_root(tmp_path):
    repo = _init(tmp_path / "repo")
    fixture_identity.configure(repo, str(tmp_path))
    assert _config(repo, "user.email") == "t@example.invalid"
    assert _config(repo, "user.name") == "t"


def test_configure_refuses_a_repo_outside_the_root_and_writes_nothing(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = _init(tmp_path / "outside")
    with pytest.raises(ValueError, match="not under"):
        fixture_identity.configure(outside, str(root))
    assert _config(outside, "user.email") == ""


def test_configure_refuses_a_path_that_is_no_repo(tmp_path):
    with pytest.raises(ValueError, match="not under"):
        fixture_identity.configure(str(tmp_path / "missing"), str(tmp_path))


@pytest.mark.parametrize("root", ["", "/missing-root-1728"])
def test_configure_refuses_a_root_that_does_not_resolve(tmp_path, root):
    repo = _init(tmp_path / "repo")
    with pytest.raises(ValueError, match="root"):
        fixture_identity.configure(repo, root)
    assert _config(repo, "user.email") == ""


def test_env_carries_one_identity_for_author_and_committer():
    env = fixture_identity.env()
    assert env["GIT_AUTHOR_EMAIL"] == env["GIT_COMMITTER_EMAIL"] == "t@example.invalid"
    assert env["GIT_AUTHOR_NAME"] == env["GIT_COMMITTER_NAME"] == "t"


def test_env_takes_a_named_identity():
    env = fixture_identity.env("Ada", "ada@example.invalid")
    assert env["GIT_COMMITTER_NAME"] == "Ada" and env["GIT_AUTHOR_EMAIL"] == "ada@example.invalid"


def test_c_args_commit_under_the_fixture_identity(tmp_path):
    repo = _init(tmp_path / "repo")
    subprocess.run(["git", "-C", repo, *fixture_identity.c_args(), "commit", "-q", "--allow-empty", "-m", "x"],
                   check=True, capture_output=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                                                         "GIT_CONFIG_SYSTEM": os.devnull})
    out = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%an <%ae>"], capture_output=True, text=True).stdout
    assert out.strip() == "t <t@example.invalid>"
