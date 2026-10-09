"""Tests for `codex-audit-range.py` (#1361): which merged PRs skipped the Codex gate for size or
the reserve ceiling since the last audit mark, and the one range a Codex audit reviews. Every test
runs the command line against a fabricated repo and ledger; nothing reaches the real ~/.cache. Runs under pytest."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_audit_fixtures import GIT_ENV, GitRepoCase, skip_row

SCRIPT = Path(__file__).resolve().parent / "codex-audit-range.py"


def pass_row(ticket, repo="skills"):
    return {"row_id": f"{repo}/{ticket}/codex-gate/1/codex-adversarial-{ticket}-gate", "origin": "append",
            "repo": repo, "ticket": ticket, "tickets": [ticket], "type": "codex-gate", "findings": [],
            "status": {"fields": {"findings": {"status": "known"}}}}


class Case(GitRepoCase):
    """A fabricated repo and ledger under `tmp`; `GitRepoCase` supplies `git` and `commit` from them."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.tmp)}  # no real ~/.gitconfig or ~/.cache
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.commit("root", "2026-09-01T00:00:00+00:00")
        self.ledger = self.tmp / "ledger.jsonl"

    def merge(self, pr, ticket, date):
        """A squash merge as GitHub writes it: the subject ends `(#<pr>)`, the body closes the ticket."""
        return self.commit(f"Work for {ticket} (#{pr})\n\n* a commit\n\nCloses #{ticket}\n", date)

    def write_ledger(self, rows):
        self.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def run_script(self, mark, *extra, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, "--ledger", self.ledger, "--repo", "skills",
                               "--base", "main", "--mark", mark, *extra],
                              cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)


@pytest.fixture
def case(tmp_path):
    return Case(tmp_path)


@pytest.fixture
def skipped(case):
    """`case` with merges on both sides of an audit mark and a ledger skipping some of them."""
    case.old = case.merge(100, 10, "2026-09-20T12:00:00+00:00")       # size, before the mark
    case.mark = case.commit("audit mark", "2026-09-25T00:00:00+00:00")
    case.size = case.merge(101, 11, "2026-09-26T12:00:00+00:00")
    case.cap = case.merge(102, 12, "2026-09-27T12:00:00+00:00")
    case.passed = case.merge(103, 13, "2026-09-28T12:00:00+00:00")
    case.ceiling = case.merge(104, 14, "2026-09-29T12:00:00+00:00")
    case.write_ledger([skip_row(10, "size"), skip_row(11, "size"),
                       skip_row(12, "codex usage 100% — capped, resets 2026-10-03 17:53"),
                       pass_row(13), skip_row(14, "ceiling"),
                       skip_row(13, "ceiling", phase="second"),  # its gate pass ran
                       skip_row(12, "size", repo="sudokupad-art")])  # merged here, but another repo's skip
    return case


def expected(c):
    return (f"range {c.mark}..{c.ceiling}\n"  # the oldest merge's parent is the mark
            f"PR #101 ticket #11 size {c.size}\n"
            f"PR #104 ticket #14 ceiling {c.ceiling}\n")


def test_a_sha_mark_lists_only_size_and_ceiling_skips_merged_after_it(skipped):
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == expected(skipped)


def test_a_date_mark_lists_the_same(skipped):
    r = skipped.run_script("2026-09-25")
    assert r.returncode == 0, r.stderr
    assert r.stdout == expected(skipped)


def test_a_skipped_ticket_with_no_merge_commit_is_named_and_the_rest_still_print(skipped):
    skipped.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling"), skip_row(99, "size")])
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == expected(skipped)
    assert "ticket #99 (size) left out: 0 merge commits on main close it" in r.stderr


def test_the_audits_own_skip_row_is_not_a_skipped_pr(skipped):
    audit_skip = {**skip_row(0, "ceiling", phase="audit"), "ticket": None, "tickets": []}
    skipped.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling"), audit_skip])
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == expected(skipped)
    assert r.stderr == ""


def test_a_pr_the_gate_could_not_measure_is_audited_like_a_size_skip(skipped):
    # An exit-30 size check leaves a PR of unknown size unreviewed, so the audit takes it (#1405 C2).
    skipped.write_ledger([skip_row(12, "unmeasured")])
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"range {skipped.size}..{skipped.cap}\nPR #102 ticket #12 unmeasured {skipped.cap}\n"


def test_a_merge_naming_the_ticket_only_in_its_subject_is_found(skipped):
    later = skipped.commit("Fix a thing (#15) (#105)\n\n* a commit with no closing line\n",
                           "2026-09-30T12:00:00+00:00")
    skipped.write_ledger([skip_row(15, "size")])
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"range {skipped.ceiling}..{later}\nPR #105 ticket #15 size {later}\n"


def test_a_ticket_closed_by_two_merges_is_named_and_left_out(skipped):
    skipped.merge(106, 11, "2026-09-30T12:00:00+00:00")
    skipped.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
    r = skipped.run_script(skipped.mark)
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"range {skipped.passed}..{skipped.ceiling}\nPR #104 ticket #14 ceiling {skipped.ceiling}\n"
    assert "ticket #11 (size) left out: 2 merge commits on main close it" in r.stderr


EMPTY = 3


def test_an_empty_ledger_exits_non_zero_saying_no_skipped_prs(case):
    case.write_ledger([])
    r = case.run_script("2026-09-01")
    assert r.returncode == EMPTY, r.stderr
    assert r.stdout == "no skipped PRs since the mark 2026-09-01: nothing to audit\n"


def test_skips_only_before_the_mark_or_of_other_reasons_exit_non_zero(case):
    case.merge(100, 10, "2026-09-20T12:00:00+00:00")
    mark = case.commit("audit mark", "2026-09-25T00:00:00+00:00")
    case.merge(102, 12, "2026-09-27T12:00:00+00:00")
    case.write_ledger([skip_row(10, "size"), skip_row(12, "codex usage 100% — capped"), pass_row(12)])
    r = case.run_script(mark)
    assert r.returncode == EMPTY, r.stderr
    assert "no skipped PRs since the mark" in r.stdout


def test_every_skipped_ticket_unmerged_exits_non_zero_and_names_each(case):
    case.write_ledger([skip_row(98, "size"), skip_row(99, "ceiling")])
    r = case.run_script("2026-09-01")
    assert r.returncode == EMPTY, r.stderr
    assert "ticket #98 (size) left out" in r.stderr
    assert "ticket #99 (ceiling) left out" in r.stderr
    assert "2 skipped ticket(s) left out undated" in r.stdout


def test_a_mark_that_is_neither_a_commit_nor_a_date_is_an_error_not_an_empty_set(case):
    case.write_ledger([skip_row(11, "size")])
    r = case.run_script("not-a-mark")
    assert r.returncode == 2
    assert "neither a commit nor an ISO date" in r.stderr


def test_outside_a_repo_is_a_git_error_not_a_bad_mark(case):
    case.write_ledger([skip_row(11, "size")])
    outside = case.tmp / "outside"
    outside.mkdir()
    r = case.run_script("not-a-mark", cwd=outside)  # git cannot answer, so the mark is not to blame
    assert r.returncode == 2
    assert "not a git repository" in r.stderr
    assert "neither a commit nor an ISO date" not in r.stderr


def test_a_missing_ledger_is_an_error_not_an_empty_set(case):
    r = case.run_script("2026-09-01")
    assert r.returncode == 2
    assert "codex-audit-range:" in r.stderr
