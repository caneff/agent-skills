"""Tests for review_cache.py (#1774): the one rule for where a repo's review files live."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_cache as rc  # noqa: E402


def test_a_directory_that_is_no_repo_raises_cache_dir_error(tmp_path):
    with pytest.raises(rc.CacheDirError, match="git cannot name the repo"):
        rc.repo_for_checkout(tmp_path)


def test_a_cwd_git_cannot_enter_raises_cache_dir_error_not_os_error(tmp_path):
    """#1735 C1: a regular file or a missing directory as the checkout is a CacheDirError, the one
    failure every caller handles, never the OSError subprocess raises before git starts."""
    plain = tmp_path / "plain"
    plain.write_text("")
    for cwd in (plain, tmp_path / "missing"):
        with pytest.raises(rc.CacheDirError, match="git cannot name the repo"):
            rc.repo_for_checkout(cwd)


def test_reviews_root_reads_home_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert rc.reviews_root() == tmp_path / ".cache" / "agent-reviews"


def test_dispositions_path_is_keyed_on_the_lowest_ticket():
    assert rc.dispositions_path("/r/skills", 1774) == "/r/skills/dispositions-1774.jsonl"


def test_write_cache_file_never_overwrites_and_sanitises_the_stem(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "REVIEWS_ROOT", tmp_path)
    first = rc.write_cache_file("skills", "brief-a/b", "one")
    second = rc.write_cache_file("skills", "brief-a/b", "two")
    assert (first.name, second.name) == ("brief-a-b.md", "brief-a-b-2.md")
    assert (first.read_text(), second.read_text()) == ("one", "two")
