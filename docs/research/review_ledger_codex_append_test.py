#!/usr/bin/env python3
"""Tests for the Codex rows the controller writes at merge (#1269): `append --type codex-<phase>`
and `harvest`, both reading the usage change from the two live readings the pass's record carries
(`usage_before`, `usage_after`, as `codex-usage-gate.py --percent` prints them). Every test runs the
command line; HOME is a temp dir, so no default path reaches the real ~/.cache."""
import json
import subprocess
import sys
import unittest

from review_ledger_codex_test import OUT_CLEAN, OUT_REFUSED, OUT_TWO, put
from review_ledger_test import SCRIPT, Case, run

STARTED, COMPLETED = "2026-09-30T09:00:00-04:00", "2026-09-30T09:02:30-04:00"
W1, W2 = 1790000000, 1790600000  # two windows' reset times


class CodexAppendCase(Case):
    def setUp(self):
        super().setUp()
        self.cache = self.tmp / "cache"
        self.ledger = self.tmp / "ledger.jsonl"
        self.skills = self.cache / "skills"

    def record(self, ticket, phase="gate", before=None, after=None, out=OUT_CLEAN, status=0):
        """A pass's record and `.out`; `before` and `after` are the readings the controller took
        (a string, or None for a record that carries none)."""
        put(self.skills, ticket, phase, STARTED, COMPLETED, out, status)
        path = self.skills / f"codex-adversarial-{ticket}-{phase}.json"
        rec = json.loads(path.read_text())
        for key, value in (("usage_before", before), ("usage_after", after)):
            if value is not None:
                rec[key] = value
        path.write_text(json.dumps(rec) + "\n")

    def append(self, ticket, phase, *extra):
        return run("append", "--repo", "skills", "--ticket", ticket, "--type", f"codex-{phase}", "--cache", self.cache,
                   "--ledger", self.ledger, *extra, home=self.home)

    def ok(self, *a):
        r = self.append(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def only_row(self):
        (row,) = self.rows().values()
        return row


class UsageChangeTest(CodexAppendCase):
    def test_a_pass_records_the_usage_change_between_its_two_readings(self):
        self.record(500, before=f"10 {W1}", after=f"12.5 {W1}", out=OUT_TWO)
        self.ok(500, "gate")
        row = self.only_row()
        self.assertEqual(row["type"], "codex-gate")
        self.assertEqual(row["cost"]["usage_delta"], {"status": "known", "before": 10.0, "after": 12.5, "delta": 2.5})
        self.assertEqual(row["cost"]["wall_clock"]["seconds"], 150)
        self.assertEqual([f["severity"] for f in row["findings"]], ["high", "medium"])

    def test_a_pass_that_used_nothing_is_a_known_zero(self):
        self.record(500, before=f"10 {W1}", after=f"10 {W1}")
        self.ok(500, "gate")
        self.assertEqual(self.only_row()["cost"]["usage_delta"]["delta"], 0)

    def test_each_phase_writes_its_own_row(self):
        for phase in ("gate", "second", "third"):
            self.record(500, phase, f"1 {W1}", f"2 {W1}")
            self.ok(500, phase)
        self.assertEqual(sorted(r["type"] for r in self.rows().values()), ["codex-gate", "codex-second", "codex-third"])

    def test_a_missing_or_unreadable_reading_is_unknown_never_zero(self):
        good = f"10 {W1}"
        cases = [(None, good), (good, None), (None, None), ("unknown", good), (good, "unknown"), ("", good),
                 ("abc", good), ("nan 5", good), (f"-3 {W1}", good), ("10", good), (f"10 {W1} x", good),
                 (good, f"inf {W1}"), (f"10 nan", good)]
        for n, (before, after) in enumerate(cases):
            self.record(510 + n, before=before, after=after)
            self.ok(510 + n, "gate")
        for row in self.rows().values():
            delta = row["cost"]["usage_delta"]
            self.assertEqual(delta["status"], "unknown", row["row_id"])
            self.assertNotIn("delta", delta)

    def test_readings_of_different_windows_are_never_subtracted(self):
        # The primary window was the worst before the pass and the secondary after: 22 -> 23 is not a 1-point cost,
        # and neither is 20 -> 25 across two windows.
        self.record(500, before=f"20 {W1}", after=f"25 {W2}")
        self.ok(500, "gate")
        delta = self.only_row()["cost"]["usage_delta"]
        self.assertEqual(delta["status"], "unknown")
        self.assertIn("different windows", delta["reason"])

    def test_a_percent_that_fell_within_one_window_is_unknown(self):
        self.record(500, before=f"90 {W1}", after=f"3 {W1}")
        self.ok(500, "gate")
        delta = self.only_row()["cost"]["usage_delta"]
        self.assertEqual(delta["status"], "unknown")
        self.assertIn("fell", delta["reason"])

    def test_a_record_with_no_readings_is_unknown(self):
        self.record(500)
        self.ok(500, "gate")
        self.assertEqual(self.only_row()["cost"]["usage_delta"]["status"], "unknown")

    def test_a_refused_run_keeps_its_usage_change_and_is_not_a_clean_pass(self):
        self.record(500, before=f"99 {W1}", after=f"100 {W1}", out=OUT_REFUSED, status=1)
        self.ok(500, "gate")
        row = self.only_row()
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "refused")
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 1.0)

    def test_no_record_for_the_phase_is_refused_and_writes_nothing(self):
        self.record(500)
        r = self.append(500, "second")
        self.assertEqual(r.returncode, 2)
        self.assertIn("expected exactly one", r.stderr)
        self.assertFalse(self.ledger.exists())

    def test_appending_the_same_pass_twice_leaves_one_row(self):
        self.record(500, before=f"1 {W1}", after=f"2 {W1}")
        self.ok(500, "gate")
        self.ok(500, "gate")
        self.assertEqual(len(self.rows()), 1)

    def test_a_later_harvest_writes_the_same_row(self):
        self.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        self.ok(500, "gate")
        appended = self.only_row()
        r = subprocess.run([sys.executable, str(SCRIPT), "harvest", "--cache", str(self.cache), "--transcripts",
                            str(self.tmp), "--ledger", str(self.ledger), "--review-file", str(self.tmp / "h.md")],
                           capture_output=True, text=True, env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({**self.only_row(), "origin": "append"}, appended)

    def test_other_rows_of_the_ticket_are_not_written(self):
        self.record(500, "gate")
        self.record(500, "second")
        self.ok(500, "gate")
        self.assertEqual([r["type"] for r in self.rows().values()], ["codex-gate"])


class SkippedPassTest(CodexAppendCase):
    def skip(self, ticket, phase, reason, *extra):
        return self.append(ticket, phase, "--skip-reason", reason, *extra)

    def test_a_skipped_pass_writes_a_row_with_its_reason_and_zero_cost(self):
        reason = "codex usage 100% - capped, resets 2026-10-03 09:00"
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", "--skip-reason", reason,
                "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.only_row()
        self.assertEqual(row["type"], "codex-gate")
        self.assertEqual(row["skip_reason"], reason)
        self.assertEqual(row["cost"]["wall_clock"], {"status": "known", "seconds": 0})
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 0)
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["status"]["fields"]["findings"], {"status": "skipped", "reason": reason})

    def test_a_skipped_pass_is_not_a_clean_pass_in_the_report(self):
        run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", "--skip-reason", "capped",
            "--ledger", self.ledger, home=self.home)
        self.record(501, before=f"1 {W1}", after=f"2 {W1}")
        self.ok(501, "gate")
        r = run("report", "--ledger", self.ledger, "--format", "json", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        (t,) = [t for t in json.loads(r.stdout)["types"] if t["type"] == "codex-gate"]
        self.assertEqual((t["rows"], t["clean_rows"], t["skipped_rows"], t["unknown_finding_rows"]), (2, 1, 1, 0))
        self.assertEqual((t["usage_percent"], t["unknown_usage_rows"]), (1.0, 0))

    def test_an_empty_reason_or_a_cache_beside_it_is_refused(self):
        for extra in (["--skip-reason", "  "], ["--skip-reason", "x", "--cache", str(self.cache)],
                      ["--skip-reason", "x", "--refusal", "y"], ["--skip-reason", "x", "--round", "2"]):
            r = run("append", "--repo", "skills", "--ticket", 500, "--type", "codex-gate", *extra,
                    "--ledger", self.ledger, home=self.home)
            self.assertEqual(r.returncode, 2, extra)
        self.assertFalse(self.ledger.exists())


class RefusalTest(CodexAppendCase):
    def test_a_refused_run_keeps_its_usage_and_holds_no_findings(self):
        self.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        self.ok(500, "gate", "--refusal", "stale: the head moved after the launch")
        row = self.only_row()
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "refused")
        self.assertEqual(row["refusal"], "stale: the head moved after the launch")
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 2.0)

    def test_a_later_harvest_keeps_the_refusal(self):
        self.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        self.ok(500, "gate", "--refusal", "raced")
        r = subprocess.run([sys.executable, str(SCRIPT), "harvest", "--cache", str(self.cache), "--transcripts",
                            str(self.tmp), "--ledger", str(self.ledger), "--review-file", str(self.tmp / "h.md")],
                           capture_output=True, text=True, env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.only_row()["findings"], [])
        self.assertEqual(self.only_row()["status"]["fields"]["findings"]["status"], "refused")

    def test_an_empty_refusal_reason_is_refused(self):
        self.record(500)
        self.assertEqual(self.append(500, "gate", "--refusal", " ").returncode, 2)
        self.assertFalse(self.ledger.exists())


class FlagTest(CodexAppendCase):
    def test_skip_and_refusal_flags_are_for_codex_types(self):
        for flags in (["--skip-reason", "x"], ["--refusal", "x"]):
            for rtype, extra in (("spec", []), ("witness-mutation", ["--mutation-id", "m1", "--outcome", "red",
                                                                     "--seconds", "1"])):
                r = run("append", "--repo", "skills", "--ticket", 500, "--type", rtype, "--cache", self.cache,
                        "--ledger", self.ledger, *flags, *extra, home=self.home)
                self.assertEqual(r.returncode, 2, (rtype, flags))
                self.assertIn("for codex types", r.stderr)
        self.assertFalse(self.ledger.exists())

    def test_mutation_flags_are_refused_on_a_codex_type_by_the_guard_not_a_missing_cache(self):
        self.record(500, before=f"1 {W1}", after=f"2 {W1}")
        r = self.append(500, "gate", "--mutation-id", "m1", "--outcome", "red", "--seconds", 3)
        self.assertEqual(r.returncode, 2)
        self.assertIn("are not for codex-gate", r.stderr)
        self.assertFalse(self.ledger.exists())

    def test_a_codex_row_is_round_one(self):
        self.record(500)
        r = self.append(500, "gate", "--round", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("round 1", r.stderr)


if __name__ == "__main__":
    unittest.main()
