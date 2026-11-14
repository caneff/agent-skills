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


def _init_repo(repo):
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "a@b.com")
    _git(repo, "config", "user.name", "Tester")
    return repo


@pytest.fixture
def repo(tmp_path):
    repo = _init_repo(str(tmp_path / "myrepo"))
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("hello\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "first commit")
    with open(os.path.join(repo, "a.txt"), "a") as f:
        f.write("world\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "second commit\n\nCloses #5\nCo-Authored-By: Claude")
    # A dotted GitHub slug, and an origin/HEAD that records the default branch.
    _git(repo, "remote", "add", "origin", "https://github.com/o/my.repo.git")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    return repo


def _page(repo, tmp_path, rng="100"):
    out = str(tmp_path / "landed.html")
    generate.main(["--roots", repo, "--out", out, rng])
    return open(out, encoding="utf-8").read()


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


def test_page_has_one_h2_per_day(tmp_path, monkeypatch):
    # Author dates are pinned, so a run across local midnight cannot move a commit
    # onto another day: two commits on one day, a third a day later.
    repo = _init_repo(str(tmp_path / "dated"))
    for i, when in enumerate(["2026-03-10T10:00:00+0000", "2026-03-10T14:00:00+0000",
                              "2026-03-11T10:00:00+0000"]):
        with open(os.path.join(repo, "a.txt"), "a") as f:
            f.write(f"{i}\n")
        _git(repo, "add", "a.txt")
        monkeypatch.setenv("GIT_AUTHOR_DATE", when)
        monkeypatch.setenv("GIT_COMMITTER_DATE", when)
        _git(repo, "commit", "-q", "-m", f"commit {i}")
    out = str(tmp_path / "landed.html")
    generate.main(["--roots", repo, "--out", out, "100"])
    page = open(out, encoding="utf-8").read()
    assert page.count('<h2 class="day"') == 2  # three commits, two days


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


def test_unset_origin_head_is_shown_as_such_not_guessed(repo, tmp_path):
    _git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    page = _page(repo, tmp_path)
    assert "origin/HEAD" in page
    assert "git remote set-head origin -a" in page
    assert "first commit" not in page  # no other branch's commits read as what landed


def test_dotted_slug_links_the_whole_name(repo, tmp_path):
    assert "https://github.com/o/my.repo/commit/" in _page(repo, tmp_path)


def test_commit_has_no_author_field():
    assert "author" not in generate.Commit.__dataclass_fields__


def _commit(**kw):
    base = dict(full_hash="f" * 40, short_hash="fffffff", date="2026-11-13 10:00",
                subject="a <subject>", body="", closes=[], agent=False,
                files=[("x.py", 3, 1)], add=3, rem=1, diff="+new\n-old\n")
    base.update(kw)
    return generate.Commit(**base)


def test_render_commit_links_hash_and_issues_when_github_is_known():
    html = generate.render_commit(_commit(closes=["7"]), "https://github.com/o/r", 4)
    assert 'href="https://github.com/o/r/commit/' + "f" * 40 + '"' in html
    assert 'href="https://github.com/o/r/issues/7"' in html
    assert "a &lt;subject&gt;" in html


def test_render_commit_without_github_has_no_links():
    html = generate.render_commit(_commit(closes=["7"]), None, 4)
    assert "href=" not in html
    assert "fffffff" not in html.split('class="meta"')[0]  # hash is not a link


def test_render_commit_marks_agent_built_and_no_description():
    html = generate.render_commit(_commit(agent=True), None, 4)
    assert "agent-built" in html
    assert "(no description)" in html
    assert "agent-built" not in generate.render_commit(_commit(), None, 4)


def test_render_commit_body_paragraphs_and_preview():
    html = generate.render_commit(_commit(body="one\n\ntwo"), None, 4)
    assert '<span class="preview">one' in html
    assert "<p class=cbody>two" in html


def test_render_commit_oversize_diff_is_skipped_with_github_link():
    c = _commit(diff=None, add=500, rem=0)
    html = generate.render_commit(c, "https://github.com/o/r", 500)
    assert "Diff skipped for size (500 changed lines)" in html
    assert "read it on GitHub" in html
    assert "dwrap" not in html


def test_render_commit_oversize_diff_without_github_has_no_link():
    html = generate.render_commit(_commit(diff=None, add=500, rem=0), None, 500)
    assert "Diff skipped for size" in html
    assert "read it on GitHub" not in html


def test_render_commit_zero_change_commit_does_not_divide_by_zero():
    html = generate.render_commit(_commit(add=0, rem=0, files=[], diff=""), None, 1)
    assert "+0 −0" in html
