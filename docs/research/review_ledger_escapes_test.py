#!/usr/bin/env python3
"""Tests for the ledger's escape measure (#1401, ADR 0005): a bug fixed on the
default branch within 14 days whose diff touches lines a reviewed PR changed is
an escape of that PR, attributed to the review components its ledger rows show
were skipped. `append --type <axis> --skip-reason` writes the skip row the
ablation needs; `escapes` reads a checkout's history and the ledger.

Every test runs the command line on a throwaway repository, with HOME in a temp
dir, so nothing here reaches the real ~/.cache or the real history."""
import json
import os
import subprocess
import unittest
from pathlib import Path

from review_ledger_test import Case, run

DAY = 86400
T0 = 1_790_000_000


class EscapeCase(Case):
    def setUp(self):
        super().setUp()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        origin = self.tmp / "origin.git"
        self.repo = self.tmp / "skills"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(self.tmp, "clone", "-q", str(origin), str(self.repo))
        self.ledger = self.tmp / "ledger.jsonl"

    def git(self, cwd, *args, when=None):
        env = dict(self.env)
        if when is not None:
            env.update(GIT_AUTHOR_DATE=f"{when} +0000", GIT_COMMITTER_DATE=f"{when} +0000")
        done = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
        assert done.returncode == 0, (args, done.stderr)
        return done.stdout.strip()

    def land(self, files, subject, day, body=""):
        """One commit on main, `day` days after T0; `files` maps path -> full text."""
        for name, text in files.items():
            (self.repo / name).write_text(text)
            self.git(self.repo, "add", name)
        message = subject + (f"\n\n{body}" if body else "")
        self.git(self.repo, "commit", "-q", "-m", message, when=T0 + day * DAY)
        return self.git(self.repo, "rev-parse", "HEAD")

    def publish(self):
        self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "remote", "set-head", "origin", "main")

    def skip(self, ticket, rtype, reason):
        r = run("append", "--repo", "skills", "--ticket", ticket, "--type", rtype, "--skip-reason", reason,
                "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    def escapes(self, *extra):
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, "--format", "json", *extra,
                home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class AxisSkipRowTest(EscapeCase):
    def test_a_skipped_axis_writes_a_row_with_its_reason_and_no_findings(self):
        self.skip(11, "standards", "ablation")
        (row,) = self.rows().values()
        self.assertEqual((row["type"], row["skip_reason"], row["findings"]), ("standards", "ablation", []))
        self.assertEqual(row["status"]["fields"]["findings"], {"status": "skipped", "reason": "ablation"})

    def test_a_skipped_axis_is_not_a_run_that_found_nothing_in_the_report(self):
        self.skip(11, "standards", "ablation")
        r = run("report", "--ledger", self.ledger, "--format", "json", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        (std,) = [t for t in json.loads(r.stdout)["types"] if t["type"] == "standards"]
        self.assertEqual((std["skipped_rows"], std["unknown_finding_rows"], std["findings"]), (1, 0, 0))

    def test_an_empty_reason_or_a_cache_alongside_it_is_refused(self):
        for extra in (["--skip-reason", "  "], ["--skip-reason", "x", "--cache", str(self.tmp)],
                      ["--skip-reason", "x", "--refusal", "y"]):
            r = run("append", "--repo", "skills", "--ticket", 11, "--type", "spec", *extra,
                    "--ledger", self.ledger, home=self.home)
            self.assertEqual(r.returncode, 2, extra)
        self.assertFalse(self.ledger.exists())

    def test_verification_cannot_be_skipped_it_is_not_a_review_axis(self):
        r = run("append", "--repo", "skills", "--ticket", 11, "--type", "verification", "--skip-reason", "x",
                "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 2)
        self.assertIn("for codex types and the review axes", r.stderr)


class EscapeTest(EscapeCase):
    def setUp(self):
        super().setUp()
        self.land({"a.py": "a1\na2\na3\na4\na5\na6\n", "b.py": "b1\nb2\nb3\nb4\nb5\nb6\n"}, "base", 0)
        # PR A (ticket 11) rewrites a.py line 2; its ledger shows the standards axis was switched off.
        self.pr_a = self.land({"a.py": "a1\nA2\na3\na4\na5\na6\n"}, "a: add the thing (#31)", 1, "Closes #11")
        self.skip(11, "standards", "ablation")
        # PR B (ticket 12) rewrites b.py line 5; its Codex pass was skipped for size.
        self.pr_b = self.land({"b.py": "b1\nb2\nb3\nb4\nB5\nb6\n"}, "b: add the other thing (#32)", 2, "Closes #12")
        self.skip(12, "codex-gate", "size")

    def test_a_fix_within_14_days_touching_a_reviewed_line_is_an_escape_of_that_pr(self):
        fix = self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        self.publish()
        got = self.escapes()
        self.assertEqual([(e["ticket"], e["fix"], e["files"]) for e in got["escapes"]], [(11, fix, ["a.py"])])
        self.assertEqual(got["escapes"][0]["days"], 3)
        self.assertEqual(got["escapes"][0]["skipped"], ["standards:ablation"])
        self.assertEqual((got["reviewed"], got["landed"], got["not_landed"]), (2, 2, []))

    def test_each_skipped_component_reports_its_prs_and_escapes(self):
        self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        self.publish()
        got = self.escapes()["by_component"]
        self.assertEqual(got, {"standards:ablation": {"prs": 1, "escapes": 1},
                               "codex-gate:size": {"prs": 1, "escapes": 0}})

    def test_a_fix_after_the_window_is_not_an_escape(self):
        self.land({"b.py": "b1\nb2\nb3\nb4\nLATE\nb6\n"}, "fix: b.py much later", 2 + 20)
        self.publish()
        self.assertEqual(self.escapes()["escapes"], [])
        # ... but a window the caller widens catches it.
        self.assertEqual(len(self.escapes("--days", "30")["escapes"]), 1)

    def test_a_commit_that_is_not_a_fix_or_touches_other_lines_is_not_an_escape(self):
        self.land({"a.py": "a1\nrefactored\na3\na4\na5\na6\n"}, "refactor: tidy a.py", 4)
        self.land({"a.py": "a1\nrefactored\na3\na4\nFIXED5\na6\n"}, "fix: an unreviewed base line", 5)
        self.publish()
        self.assertEqual(self.escapes()["escapes"], [])

    def test_a_fix_pattern_the_caller_names_replaces_the_default(self):
        self.land({"a.py": "a1\nPATCHED\na3\na4\na5\na6\n"}, "patch: crash in a.py", 4)
        self.publish()
        self.assertEqual(self.escapes()["escapes"], [])
        self.assertEqual(len(self.escapes("--fix-pattern", "^patch")["escapes"]), 1)

    def test_a_reviewed_ticket_that_never_landed_is_named_not_counted_as_clean(self):
        self.skip(99, "spec", "ablation")
        self.publish()
        got = self.escapes()
        self.assertEqual(got["not_landed"], [99])
        self.assertEqual(got["reviewed"], 3)
        self.assertEqual(got["landed"], 2)

    def test_a_file_name_with_a_space_or_non_ascii_letters_is_attributed_not_fatal(self):
        # #1401 C3: names come from `--name-only -z`, not from a patch header.
        self.land({"Sticker Final é.json": "x1\nx2\nx3\n"}, "c: add the sticker (#33)", 3, "Closes #13")
        self.skip(13, "spec", "ablation")
        self.land({"Sticker Final é.json": "x1\nFIX\nx3\n"}, "fix: sticker", 4)
        self.publish()
        got = self.escapes()
        self.assertEqual([(e["ticket"], e["files"]) for e in got["escapes"]], [(13, ["Sticker Final é.json"])])

    def test_a_removed_line_that_looks_like_a_patch_header_is_not_misread(self):
        self.land({"d.txt": "d1\n-- not a header\nd3\n"}, "d: add (#34)", 3, "Closes #14")
        self.skip(14, "spec", "ablation")
        self.land({"d.txt": "d1\nFIXED\nd3\n"}, "fix: d", 4)
        self.publish()
        self.assertEqual([e["files"] for e in self.escapes()["escapes"]], [["d.txt"]])

    def test_a_fix_that_only_inserts_lines_is_attributed_to_the_lines_around_it(self):
        self.land({"a.py": "a1\nA2\ninserted\na3\na4\na5\na6\n"}, "fix: missing guard in a.py", 4)
        self.publish()
        self.assertEqual([e["ticket"] for e in self.escapes()["escapes"]], [11])

    def test_a_landing_is_found_by_the_ticket_in_its_subject_when_the_body_has_no_closes(self):
        self.land({"e.py": "e1\ne2\ne3\n"}, "e: add the thing (#15) (#35)", 3)
        self.skip(15, "spec", "ablation")
        self.land({"e.py": "e1\nFIXED\ne3\n"}, "fix: e", 4)
        self.publish()
        got = self.escapes()
        self.assertEqual(([e["ticket"] for e in got["escapes"]], got["not_landed"]), ([15], []))

    def test_the_oldest_landing_is_the_pr_and_a_later_mention_is_a_follow_up(self):
        # The follow-up commit says `Closes #11` too, later; blame points at the first landing.
        self.land({"a.py": "a1\nA2\na3\na4\na5\na6\n", "g.txt": "g\n"}, "g: follow-up (#36)", 3, "Closes #11")
        self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: a.py", 4)
        self.publish()
        (e,) = self.escapes()["escapes"]
        self.assertEqual((e["ticket"], e["landing"]), (11, self.pr_a))

    def test_a_merge_commit_is_not_a_fix_commit(self):
        self.git(self.repo, "checkout", "-q", "-b", "side")
        self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "side work", 4)
        self.git(self.repo, "checkout", "-q", "main")
        self.land({"z.txt": "z\n"}, "z: unrelated", 5)
        self.git(self.repo, "merge", "-q", "--no-ff", "-m", "fix: merge the side branch", "side", when=T0 + 6 * DAY)
        self.publish()
        self.assertEqual(self.escapes()["escapes"], [])

    def test_a_sweep_commit_is_not_an_escape_whatever_its_subject_says(self):
        self.land({"a.py": "a1\nSWEPT\na3\na4\na5\na6\n"}, "Sweep: fix leftovers from burn x", 4)
        self.publish()
        self.assertEqual(self.escapes()["escapes"], [])

    def test_components_are_named_by_a_known_reason_and_free_text_is_one_other(self):
        self.skip(16, "codex-gate", "codex usage 71% at or above reserve ceiling 70%, resets 2026-10-05")
        self.land({"h.txt": "h\n"}, "h (#37)", 3, "Closes #16")
        self.publish()
        self.assertIn("codex-gate:other", self.escapes()["by_component"])

    def test_origin_is_fetched_first_so_a_fix_pushed_from_elsewhere_counts(self):
        other = self.tmp / "elsewhere"
        self.git(self.tmp, "clone", "-q", str(self.tmp / "origin.git"), str(other))
        self.publish()  # PR A and B are on origin; the fix arrives only through `other`
        self.git(other, "pull", "-q", "origin", "main")
        (other / "a.py").write_text("a1\nFIXED\na3\na4\na5\na6\n")
        self.git(other, "add", "a.py")
        self.git(other, "commit", "-q", "-m", "fix: a.py", when=T0 + 4 * DAY)
        self.git(other, "push", "-q", "origin", "main")
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, "--format", "json", "--no-fetch",
                home=self.home)
        self.assertEqual(json.loads(r.stdout)["escapes"], [])  # origin as this checkout last saw it
        self.assertEqual(len(self.escapes()["escapes"]), 1)  # fetched first

    def test_a_git_failure_is_refused_not_counted_as_fewer_escapes(self):
        self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        self.publish()
        self.git(self.repo, "remote", "set-url", "origin", str(self.tmp / "no-such.git"))
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 2)
        self.assertIn("git fetch", r.stderr)

    def test_no_default_branch_recorded_is_refused_by_name(self):
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 2)
        self.assertIn("origin/HEAD", r.stderr)

    def test_a_missing_ledger_is_refused_not_read_as_no_escapes(self):
        self.publish()
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.tmp / "none.jsonl", home=self.home)
        self.assertEqual(r.returncode, 2)

    def test_markdown_output_names_the_decision_rule_inputs(self):
        self.land({"a.py": "a1\nFIXED\na3\na4\na5\na6\n"}, "fix: crash in a.py", 4)
        self.publish()
        r = run("escapes", "--repo-dir", self.repo, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| standards:ablation | 1 | 1 |", r.stdout)
        self.assertIn("1 escape(s)", r.stdout)


if __name__ == "__main__":
    unittest.main()
