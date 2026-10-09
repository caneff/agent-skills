"""Tests for `gitcmd.py` (#1405 S6): the one git helper of the Codex audit's
scripts."""
import subprocess

import pytest

from gitcmd import GitError, git


@pytest.fixture(autouse=True)
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)


def test_success_returns_the_result():
    assert git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def test_a_failure_raises_with_the_command_and_stderr():
    with pytest.raises(GitError) as e:
        git("rev-parse", "--verify", "nope")
    assert str(e.value).startswith("git rev-parse --verify nope: "), str(e.value)


def test_an_exit_named_as_an_answer_is_returned_and_any_other_still_raises():
    assert git("rev-parse", "--verify", "--quiet", "nope^{commit}", ok=(0, 1)).returncode == 1
    with pytest.raises(GitError):  # exit 129 is a usage error, not the answer 1
        git("merge-base", "--no-such-flag", ok=(0, 1))
    with pytest.raises(GitError):
        git("merge-base", "--is-ancestor", "nope", "nope2", ok=(0, 1))  # exit 128: not a commit
