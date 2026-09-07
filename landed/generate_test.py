#!/usr/bin/env python3
"""Tests for the landed page generator (#612) — builds a tmp git repo with a
couple of commits and checks the rendered page, not by running the CLI
against the real ~/src workspace. Plain-assert style, run directly with
python3 (not yet picked up by tests/all.sh's *.test.sh / *_audit.py rules —
slice #609 adds *_test.py discovery).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import generate  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _make_repo(tmp):
    repo = os.path.join(tmp, "myrepo")
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


def test_page_contains_commit_subjects_and_hashes():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        out = os.path.join(tmp, "landed.html")
        rc = generate.main(["--roots", repo, "--out", out, "100"])
        assert rc == 0
        page = open(out, encoding="utf-8").read()
        assert "first commit" in page
        assert "second commit" in page
        short_hash = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%h"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert short_hash in page


def test_page_has_one_h2_per_day():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        out = os.path.join(tmp, "landed.html")
        generate.main(["--roots", repo, "--out", out, "100"])
        page = open(out, encoding="utf-8").read()
        assert page.count('<h2 class="day"') == 1  # both commits land the same day


def test_page_links_the_shell_assets_and_writes_them_beside_it():
    """#613: the page comes from the harness shell, which links assets/ —
    so the generator delivers those files next to the page it wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        out = os.path.join(tmp, "landed.html")
        generate.main(["--roots", repo, "--out", out, "100"])
        page = open(out, encoding="utf-8").read()
        assert '<link rel="stylesheet" href="assets/base/base.css">' in page
        assert os.path.isfile(os.path.join(tmp, "assets", "base", "base.css"))
        assert os.path.isfile(os.path.join(tmp, "assets", "components", "callout", "callout.css"))


def test_no_commits_in_range_writes_nothing_and_returns_1():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        out = os.path.join(tmp, "landed.html")
        rc = generate.main(["--roots", repo, "--out", out, "HEAD..HEAD"])
        assert rc == 1
        assert not os.path.exists(out)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
