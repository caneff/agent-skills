"""Tests for review_cache.py (#1774): the one rule for where a repo's review files live."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_cache as rc  # noqa: E402


def test_fold_repo_folds_the_alias_and_leaves_other_names():
    assert (rc.fold_repo("agent-skills"), rc.fold_repo("skills"), rc.fold_repo("other")) == \
        ("skills", "skills", "other")


def test_repo_for_checkout_names_the_repo_not_the_worktree(tmp_path):
    main = tmp_path / "agent-skills"
    main.mkdir()
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    wt = tmp_path / "elsewhere"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "--detach", str(wt)], check=True)
    assert rc.repo_for_checkout(wt) == "skills"
    assert rc.cache_dir_for(wt) == rc.REVIEWS_ROOT / "skills"


def test_a_directory_that_is_no_repo_raises_cache_dir_error(tmp_path):
    with pytest.raises(rc.CacheDirError, match="git cannot name the repo"):
        rc.repo_for_checkout(tmp_path)


def test_dispositions_path_is_keyed_on_the_lowest_ticket():
    assert rc.dispositions_path("/r/skills", 1774) == "/r/skills/dispositions-1774.jsonl"


def test_write_cache_file_never_overwrites_and_sanitises_the_stem(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "REVIEWS_ROOT", tmp_path)
    first = rc.write_cache_file("skills", "brief-a/b", "one")
    second = rc.write_cache_file("skills", "brief-a/b", "two")
    assert (first.name, second.name) == ("brief-a-b.md", "brief-a-b-2.md")
    assert (first.read_text(), second.read_text()) == ("one", "two")
