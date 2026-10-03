#!/usr/bin/env python3
"""Tests for `codex-audit-range.py` (#1361): which merged PRs skipped the Codex gate for size or
the reserve ceiling since the last audit mark, and the one range a Codex audit reviews. Every test
runs the command line against a fabricated repo and ledger; nothing reaches the real ~/.cache."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "codex-audit-range.py"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def skip_row(ticket, reason, repo="skills", phase="gate"):
    """A ledger row as `review_ledger.py append --skip-reason` writes it (the fields the script reads)."""
    return {"row_id": f"{repo}/{ticket}/codex-{phase}/1/codex-skipped-{ticket}-{phase}", "origin": "append",
            "repo": repo, "ticket": ticket, "tickets": [ticket], "type": f"codex-{phase}", "findings": [],
            "skip_reason": reason,
            "status": {"fields": {"findings": {"status": "skipped", "reason": reason}}}}


def pass_row(ticket, repo="skills"):
    return {"row_id": f"{repo}/{ticket}/codex-gate/1/codex-adversarial-{ticket}-gate", "origin": "append",
            "repo": repo, "ticket": ticket, "tickets": [ticket], "type": "codex-gate", "findings": [],
            "status": {"fields": {"findings": {"status": "known"}}}}


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.tmp)}  # no real ~/.gitconfig or ~/.cache
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.commit("root", "2026-09-01T00:00:00+00:00")
        self.ledger = self.tmp / "ledger.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, date=None):
        env = {**self.env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
        return subprocess.run(["git", *args], cwd=self.repo, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message, date):
        (self.repo / "f").write_text(message)
        self.git("add", "f")
        self.git("commit", "-q", "-m", message, date=date)
        return self.git("rev-parse", "HEAD")

    def merge(self, pr, ticket, date):
        """A squash merge as GitHub writes it: the subject ends `(#<pr>)`, the body closes the ticket."""
        return self.commit(f"Work for {ticket} (#{pr})\n\n* a commit\n\nCloses #{ticket}\n", date)

    def write_ledger(self, rows):
        self.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def run_script(self, mark, *extra, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, "--ledger", self.ledger, "--repo", "skills",
                               "--base", "main", "--mark", mark, *extra],
                              cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)


class SkippedSinceMarkTest(Case):
    def setUp(self):
        super().setUp()
        self.old = self.merge(100, 10, "2026-09-20T12:00:00+00:00")       # size, before the mark
        self.mark = self.commit("audit mark", "2026-09-25T00:00:00+00:00")
        self.size = self.merge(101, 11, "2026-09-26T12:00:00+00:00")
        self.cap = self.merge(102, 12, "2026-09-27T12:00:00+00:00")
        self.passed = self.merge(103, 13, "2026-09-28T12:00:00+00:00")
        self.ceiling = self.merge(104, 14, "2026-09-29T12:00:00+00:00")
        self.write_ledger([skip_row(10, "size"), skip_row(11, "size"),
                           skip_row(12, "codex usage 100% — capped, resets 2026-10-03 17:53"),
                           pass_row(13), skip_row(14, "ceiling"),
                           skip_row(13, "ceiling", phase="second"),  # its gate pass ran
                           skip_row(12, "size", repo="sudokupad-art")])  # merged here, but another repo's skip

    def expected(self):
        return (f"range {self.mark}..{self.ceiling}\n"  # the oldest merge's parent is the mark
                f"PR #101 ticket #11 size {self.size}\n"
                f"PR #104 ticket #14 ceiling {self.ceiling}\n")

    def test_a_sha_mark_lists_only_size_and_ceiling_skips_merged_after_it(self):
        r = self.run_script(self.mark)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, self.expected())

    def test_a_date_mark_lists_the_same(self):
        r = self.run_script("2026-09-25")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, self.expected())


    def test_a_skipped_ticket_with_no_merge_commit_is_named_and_the_rest_still_print(self):
        self.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling"), skip_row(99, "size")])
        r = self.run_script(self.mark)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, self.expected())
        self.assertIn("ticket #99 (size) left out: 0 merge commits on main close it", r.stderr)

    def test_the_audits_own_skip_row_is_not_a_skipped_pr(self):
        audit_skip = {**skip_row(0, "ceiling", phase="audit"), "ticket": None, "tickets": []}
        self.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling"), audit_skip])
        r = self.run_script(self.mark)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, self.expected())
        self.assertEqual(r.stderr, "")

    def test_a_merge_naming_the_ticket_only_in_its_subject_is_found(self):
        later = self.commit("Fix a thing (#15) (#105)\n\n* a commit with no closing line\n",
                            "2026-09-30T12:00:00+00:00")
        self.write_ledger([skip_row(15, "size")])
        r = self.run_script(self.mark)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, f"range {self.ceiling}..{later}\nPR #105 ticket #15 size {later}\n")

    def test_a_ticket_closed_by_two_merges_is_named_and_left_out(self):
        self.merge(106, 11, "2026-09-30T12:00:00+00:00")
        self.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
        r = self.run_script(self.mark)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, f"range {self.passed}..{self.ceiling}\nPR #104 ticket #14 ceiling {self.ceiling}\n")
        self.assertIn("ticket #11 (size) left out: 2 merge commits on main close it", r.stderr)


class NothingToAuditTest(Case):
    EMPTY = 3

    def test_an_empty_ledger_exits_non_zero_saying_no_skipped_prs(self):
        self.write_ledger([])
        r = self.run_script("2026-09-01")
        self.assertEqual(r.returncode, self.EMPTY, r.stderr)
        self.assertEqual(r.stdout, "no skipped PRs since the mark 2026-09-01: nothing to audit\n")

    def test_skips_only_before_the_mark_or_of_other_reasons_exit_non_zero(self):
        self.merge(100, 10, "2026-09-20T12:00:00+00:00")
        mark = self.commit("audit mark", "2026-09-25T00:00:00+00:00")
        self.merge(102, 12, "2026-09-27T12:00:00+00:00")
        self.write_ledger([skip_row(10, "size"), skip_row(12, "codex usage 100% — capped"), pass_row(12)])
        r = self.run_script(mark)
        self.assertEqual(r.returncode, self.EMPTY, r.stderr)
        self.assertIn("no skipped PRs since the mark", r.stdout)

    def test_every_skipped_ticket_unmerged_exits_non_zero_and_names_each(self):
        self.write_ledger([skip_row(98, "size"), skip_row(99, "ceiling")])
        r = self.run_script("2026-09-01")
        self.assertEqual(r.returncode, self.EMPTY, r.stderr)
        self.assertIn("ticket #98 (size) left out", r.stderr)
        self.assertIn("ticket #99 (ceiling) left out", r.stderr)
        self.assertIn("2 skipped ticket(s) left out undated", r.stdout)


class BadInputTest(Case):
    def test_a_mark_that_is_neither_a_commit_nor_a_date_is_an_error_not_an_empty_set(self):
        self.write_ledger([skip_row(11, "size")])
        r = self.run_script("not-a-mark")
        self.assertEqual(r.returncode, 2)
        self.assertIn("neither a commit nor an ISO date", r.stderr)

    def test_outside_a_repo_is_a_git_error_not_a_bad_mark(self):
        self.write_ledger([skip_row(11, "size")])
        outside = self.tmp / "outside"
        outside.mkdir()
        r = self.run_script("not-a-mark", cwd=outside)  # git cannot answer, so the mark is not to blame
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a git repository", r.stderr)
        self.assertNotIn("neither a commit nor an ISO date", r.stderr)

    def test_a_missing_ledger_is_an_error_not_an_empty_set(self):
        r = self.run_script("2026-09-01")
        self.assertEqual(r.returncode, 2)
        self.assertIn("codex-audit-range:", r.stderr)


if __name__ == "__main__":
    unittest.main()
