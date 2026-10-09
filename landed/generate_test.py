"""Tests for the landed page generator (#612) — builds a tmp git repo with a
couple of commits and checks the rendered page, not by running the CLI
against the real ~/src workspace.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import generate  # noqa: E402


# A caller's leaked GIT_DIR/GIT_WORK_TREE would redirect every call below at
# that repo instead of the tmp one (#622); scrub them out of the subprocess env.
_GIT_ENV_LEAKS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_LEAKS}
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    repo = str(tmp_path / "myrepo")
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@b.com")
    _git(repo, "config", "user.name", "Tester")
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("hello\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "first commit")
    with open(os.path.join(repo, "a.txt"), "a") as f:
        f.write("world\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "second commit\n\nCloses #5\nCo-Authored-By: Claude")
    return repo


def test_page_contains_commit_subjects_and_hashes(repo, tmp_path):
    out = str(tmp_path / "landed.html")
    rc = generate.main(["--roots", repo, "--out", out, "100"])
    assert rc == 0
    page = open(out, encoding="utf-8").read()
    assert "first commit" in page
    assert "second commit" in page
    short_hash = subprocess.run(
        ["git", "-C", repo, "log", "-1", "--format=%h"],
        capture_output=True, text=True, check=True,
        env={k: v for k, v in os.environ.items() if k not in _GIT_ENV_LEAKS},
    ).stdout.strip()
    assert short_hash in page


def test_page_has_one_h2_per_day(repo, tmp_path):
    out = str(tmp_path / "landed.html")
    generate.main(["--roots", repo, "--out", out, "100"])
    page = open(out, encoding="utf-8").read()
    assert page.count('<h2 class="day"') == 1  # both commits land the same day


def test_page_links_the_shell_assets_and_writes_them_beside_it(repo, tmp_path):
    """#613: the page comes from the harness shell, which links assets/ —
    so the generator delivers those files next to the page it wrote."""
    out = str(tmp_path / "landed.html")
    generate.main(["--roots", repo, "--out", out, "100"])
    page = open(out, encoding="utf-8").read()
    assert '<link rel="stylesheet" href="assets/base/base.css">' in page
    assert (tmp_path / "assets" / "base" / "base.css").is_file()
    assert (tmp_path / "assets" / "components" / "callout" / "callout.css").is_file()


def test_no_commits_in_range_writes_nothing_and_returns_1(repo, tmp_path):
    out = str(tmp_path / "landed.html")
    rc = generate.main(["--roots", repo, "--out", out, "HEAD..HEAD"])
    assert rc == 1
    assert not os.path.exists(out)
