"""Contract tests for flow/bin/repo-hygiene (#2013).

Each test runs the command as Chris would, against a throwaway git repo with a
bare origin and a stub `gh` on PATH that answers from fixture files. Nothing
touches a real repo or the network.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../common"))
import fixture_identity  # noqa: E402

SCRIPT = Path(__file__).with_name("repo-hygiene")

STUB_GH = """#!/usr/bin/env bash
# Answers `gh <noun> list` from $HYG_FIX/<noun>.json; $HYG_FIX/fail-<noun> makes it fail.
noun="$1"
[ -e "$HYG_FIX/fail-$noun" ] && { echo "gh: HTTP 401" >&2; exit 1; }
cat "$HYG_FIX/$noun.json"
"""


def git(cwd, *args):
    env = {**os.environ, **fixture_identity.env()}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True, env=env).stdout


class World:
    def __init__(self, tmp):
        self.tmp = tmp
        self.origin = tmp / "origin.git"
        self.repo = tmp / "repo"
        self.fix = tmp / "fix"
        self.bin = tmp / "bin"
        self.fix.mkdir()
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(STUB_GH)
        gh.chmod(0o755)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        fixture_identity.configure(str(self.repo), str(tmp))
        git(self.repo, "remote", "add", "origin", "https://github.com/caneff/demo.git")
        git(self.repo, "config", "url." + str(self.origin) + ".insteadOf", "https://github.com/caneff/demo.git")
        (self.repo / "a.txt").write_text("a\n")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.gh(pr=[], issue=[], run=[])

    def gh(self, **nouns):
        for noun, data in nouns.items():
            (self.fix / f"{noun}.json").write_text(json.dumps(data))

    def fail(self, noun):
        (self.fix / f"fail-{noun}").write_text("")

    def run(self, *args, path=None):
        env = {**os.environ, "HYG_FIX": str(self.fix),
               "PATH": f"{self.bin}:{path or os.environ['PATH']}"}
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
                              capture_output=True, text=True, env=env)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def section(out, name):
    """The lines under `== name ==`, up to the next heading."""
    lines = out.splitlines()
    start = lines.index(f"== {name} ==") + 1
    body = []
    for line in lines[start:]:
        if line.startswith("== "):
            break
        body.append(line)
    return "\n".join(body)


def test_clean_repo_reports_every_check_as_ran_and_exits_zero(world):
    r = world.run()
    assert r.returncode == 0, r.stderr
    for name in ("worktrees", "branches", "scheduled runs", "unlabelled tickets",
                 "bot tickets", "ignored folders"):
        assert section(r.stdout, name).strip() == "none", name


def test_no_gh_on_path_says_the_gh_checks_did_not_run_never_none(world):
    (world.bin / "gh").unlink()
    r = world.run(path="/usr/bin:/bin")
    assert r.returncode == 3
    for name in ("worktrees", "scheduled runs", "unlabelled tickets", "bot tickets"):
        body = section(r.stdout, name)
        assert body.startswith("did not run:"), (name, body)
        assert "none" not in body
    assert "gh" in section(r.stdout, "scheduled runs")


def test_one_failing_gh_call_fails_only_its_own_checks(world):
    world.fail("run")
    r = world.run()
    assert r.returncode == 3
    assert section(r.stdout, "scheduled runs").startswith("did not run:")
    assert section(r.stdout, "unlabelled tickets").strip() == "none"


def test_dirty_worktree_without_a_pr_is_listed_and_a_pr_clears_it(world, tmp_path):
    wt = tmp_path / "wt"
    git(world.repo, "worktree", "add", "-q", "-b", "implement-7", str(wt))
    (wt / "new.txt").write_text("wip\n")
    r = world.run()
    assert "implement-7" in section(r.stdout, "worktrees")
    assert "uncommitted" in section(r.stdout, "worktrees")
    world.gh(pr=[{"number": 9, "headRefName": "implement-7"}])
    r = world.run()
    assert section(r.stdout, "worktrees").strip() == "none"


def test_clean_worktree_without_a_pr_is_not_listed(world, tmp_path):
    git(world.repo, "worktree", "add", "-q", "-b", "implement-8", str(tmp_path / "wt"))
    assert section(world.run().stdout, "worktrees").strip() == "none"


def test_merged_branch_is_listed_with_the_delete_it_would_run(world):
    git(world.repo, "branch", "old-merged")
    r = world.run()
    body = section(r.stdout, "branches")
    assert "old-merged" in body
    assert "merged into origin/main" in body
    assert f"! git -C {world.repo} branch -d old-merged" in body
    assert subprocess.run(["git", "-C", str(world.repo), "rev-parse", "--verify", "old-merged"],
                          capture_output=True).returncode == 0, "the command must not delete"


def test_old_unmerged_branch_without_a_pr_is_listed_without_a_delete_line(world):
    git(world.repo, "checkout", "-q", "-b", "stale-work")
    (world.repo / "b.txt").write_text("b\n")
    git(world.repo, "add", "b.txt")
    old = "2020-01-01T00:00:00"
    env = {**os.environ, **fixture_identity.env(), "GIT_AUTHOR_DATE": old, "GIT_COMMITTER_DATE": old}
    subprocess.run(["git", "-C", str(world.repo), "commit", "-q", "-m", "old"],
                   check=True, env=env)
    git(world.repo, "checkout", "-q", "main")
    body = section(world.run().stdout, "branches")
    assert "stale-work" in body and "unmerged" in body
    assert "branch -d stale-work" not in body
    world.gh(pr=[{"number": 3, "headRefName": "stale-work"}])
    assert section(world.run().stdout, "branches").strip() == "none"


def test_red_scheduled_run_is_listed_only_when_it_is_the_latest_of_its_workflow(world):
    world.gh(run=[
        {"workflowName": "nightly", "conclusion": "failure", "status": "completed",
         "url": "https://x/1", "createdAt": "2026-11-20T00:00:00Z"},
        {"workflowName": "nightly", "conclusion": "success", "status": "completed",
         "url": "https://x/2", "createdAt": "2026-11-21T00:00:00Z"},
        {"workflowName": "audit", "conclusion": "failure", "status": "completed",
         "url": "https://x/3", "createdAt": "2026-11-22T00:00:00Z"},
    ])
    body = section(world.run().stdout, "scheduled runs")
    assert "audit" in body and "https://x/3" in body
    assert "nightly" not in body


def test_unlabelled_ticket_is_listed(world):
    world.gh(issue=[
        {"number": 5, "title": "no label", "labels": [], "author": {"login": "caneff", "is_bot": False},
         "comments": [], "assignees": []},
        {"number": 6, "title": "has label", "labels": [{"name": "backlog"}],
         "author": {"login": "caneff", "is_bot": False}, "comments": [], "assignees": []},
    ])
    body = section(world.run().stdout, "unlabelled tickets")
    assert "#5" in body and "no label" in body
    assert "#6" not in body


def test_bot_ticket_with_no_comment_and_no_assignee_is_listed(world):
    bot = {"login": "app/sweeper", "is_bot": True}
    lab = [{"name": "needs-triage"}]
    world.gh(issue=[
        {"number": 11, "title": "unread", "labels": lab, "author": bot, "comments": [], "assignees": []},
        {"number": 12, "title": "answered", "labels": lab, "author": bot,
         "comments": [{"body": "seen"}], "assignees": []},
        {"number": 13, "title": "taken", "labels": lab, "author": bot,
         "comments": [], "assignees": [{"login": "caneff"}]},
    ])
    body = section(world.run().stdout, "bot tickets")
    assert "#11" in body
    assert "#12" not in body and "#13" not in body


def test_big_ignored_folder_is_listed_with_size_and_the_rm_it_would_run(world):
    (world.repo / ".gitignore").write_text("cache/\n")
    git(world.repo, "add", ".gitignore")
    git(world.repo, "commit", "-q", "-m", "ignore")
    (world.repo / "cache").mkdir()
    (world.repo / "cache" / "blob").write_bytes(b"x" * 2_000_000)
    r = world.run("--min-ignored-mb", "1")
    body = section(r.stdout, "ignored folders")
    assert "cache" in body and "MB" in body
    assert f"! rm -r -- {world.repo}/cache" in body
    assert (world.repo / "cache" / "blob").exists(), "the command must not delete"
    assert section(world.run().stdout, "ignored folders").strip() == "none"


def test_repo_without_a_github_remote_says_the_gh_checks_did_not_run(world):
    git(world.repo, "remote", "set-url", "origin", str(world.origin))
    r = world.run()
    assert r.returncode == 3
    assert "GitHub remote" in section(r.stdout, "unlabelled tickets")
