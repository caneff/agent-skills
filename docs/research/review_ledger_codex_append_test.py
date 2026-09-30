#!/usr/bin/env python3
"""Tests for `review_ledger.py append --type codex-<phase>` (#1269): one row per Codex pass the
controller runs at merge, carrying the usage change read with the gate's own reader. Every test
runs the command line. HOME and CODEX_HOME are temp dirs and PATH holds no `codex`, so the usage
reader answers from a fixture cache or not at all, and never reaches a real Codex."""
import json
import os
import subprocess
import sys
import time
import unittest

from review_ledger_codex_test import OUT_CLEAN, OUT_REFUSED, OUT_TWO, put
from review_ledger_test import SCRIPT, Case

DAY = 86400
STARTED, COMPLETED = "2026-09-30T09:00:00-04:00", "2026-09-30T09:02:30-04:00"


def run_append(*args, home, usage=None):
    """The command line with `usage` (a percent, or None for no readable usage) as the weekly window."""
    codex_home = home / "codex"
    codex_home.mkdir(exist_ok=True)
    cache = codex_home / "usage-cache.json"
    cache.unlink(missing_ok=True)
    if usage is not None:
        now = time.time()
        cache.write_text(json.dumps({"fetchedAt": now, "primary": None,
                                     "secondary": {"usedPercent": usage, "resetsAt": now + DAY}}))
    env = {"HOME": str(home), "CODEX_HOME": str(codex_home), "PATH": "/nonexistent"}
    return subprocess.run([sys.executable, str(SCRIPT), "append", *map(str, args)],
                          capture_output=True, text=True, env=env)


class CodexAppendCase(Case):
    def setUp(self):
        super().setUp()
        self.cache = self.tmp / "cache"
        self.ledger = self.tmp / "ledger.jsonl"
        self.skills = self.cache / "skills"

    def append(self, ticket, phase, *extra, usage=None, before="10"):
        args = ["--repo", "skills", "--ticket", ticket, "--type", f"codex-{phase}", "--cache", self.cache,
                "--ledger", self.ledger, *extra]
        if before is not None:
            args += ["--usage-before", before]
        return run_append(*args, home=self.home, usage=usage)

    def ok(self, *a, **k):
        r = self.append(*a, **k)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def only_row(self):
        (row,) = self.rows().values()
        return row


class UsageChangeTest(CodexAppendCase):
    def test_a_pass_records_the_usage_change_before_to_after(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_TWO)
        self.ok(500, "gate", before="10", usage=12.5)
        row = self.only_row()
        self.assertEqual(row["type"], "codex-gate")
        self.assertEqual(row["cost"]["usage_delta"], {"status": "known", "before": 10.0, "after": 12.5, "delta": 2.5})
        self.assertEqual(row["cost"]["wall_clock"]["seconds"], 150)
        self.assertEqual([f["severity"] for f in row["findings"]], ["high", "medium"])

    def test_a_pass_that_used_nothing_is_a_known_zero(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(500, "gate", before="10", usage=10)
        self.assertEqual(self.only_row()["cost"]["usage_delta"]["delta"], 0)

    def test_each_phase_writes_its_own_row(self):
        for phase in ("gate", "second", "third"):
            put(self.skills, 500, phase, STARTED, COMPLETED, OUT_CLEAN)
            self.ok(500, phase, usage=11)
        self.assertEqual(sorted(r["type"] for r in self.rows().values()), ["codex-gate", "codex-second", "codex-third"])

    def test_a_failed_read_after_the_pass_is_unknown_never_zero(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(500, "gate", before="10", usage=None)
        delta = self.only_row()["cost"]["usage_delta"]
        self.assertEqual(delta["status"], "unknown")
        self.assertNotIn("delta", delta)

    def test_a_missing_or_unreadable_before_is_unknown_never_zero(self):
        for n, before in enumerate([None, "unknown", "", "abc", "nan", "-3"]):
            put(self.skills, 510 + n, "gate", STARTED, COMPLETED, OUT_CLEAN)
            self.ok(510 + n, "gate", before=before, usage=12)
        for row in self.rows().values():
            self.assertEqual(row["cost"]["usage_delta"]["status"], "unknown", row["row_id"])
            self.assertNotIn("delta", row["cost"]["usage_delta"])

    def test_a_percent_that_fell_is_a_window_reset_not_a_negative_cost(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(500, "gate", before="90", usage=3)
        delta = self.only_row()["cost"]["usage_delta"]
        self.assertEqual(delta["status"], "unknown")
        self.assertIn("reset", delta["reason"])

    def test_a_refused_run_keeps_its_usage_change_and_is_not_a_clean_pass(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_REFUSED, status=1)
        self.ok(500, "gate", before="99", usage=100)
        row = self.only_row()
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "refused")
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 1.0)

    def test_no_record_for_the_phase_is_refused_and_writes_nothing(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        r = self.append(500, "second", usage=12)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no Codex record", r.stderr)
        self.assertFalse(self.ledger.exists())

    def test_appending_the_same_pass_twice_leaves_one_row(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(500, "gate", usage=12)
        self.ok(500, "gate", usage=13)
        self.assertEqual(len(self.rows()), 1)

    def test_a_later_harvest_keeps_the_appended_usage_change(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_TWO)
        self.ok(500, "gate", before="10", usage=12)
        r = subprocess.run([sys.executable, str(SCRIPT), "harvest", "--cache", str(self.cache), "--transcripts",
                            str(self.tmp), "--ledger", str(self.ledger), "--review-file", str(self.tmp / "h.md")],
                           capture_output=True, text=True, env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.only_row()["cost"]["usage_delta"]["delta"], 2.0)
        self.assertEqual(len(self.only_row()["findings"]), 2)

    def test_other_rows_of_the_ticket_are_not_written_or_lost(self):
        put(self.skills, 500, "gate", STARTED, COMPLETED, OUT_CLEAN)
        put(self.skills, 500, "second", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(500, "gate", usage=12)
        self.assertEqual([r["type"] for r in self.rows().values()], ["codex-gate"])


class SkippedPassTest(CodexAppendCase):
    def skip(self, ticket, phase, reason, **k):
        return self.append(ticket, phase, "--skip-reason", reason, **k)

    def test_a_skipped_pass_writes_a_row_with_its_reason_and_zero_cost(self):
        r = self.skip(500, "gate", "codex usage 100% - capped, resets 2026-10-03 09:00", before=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.only_row()
        self.assertEqual(row["type"], "codex-gate")
        self.assertEqual(row["skip_reason"], "codex usage 100% - capped, resets 2026-10-03 09:00")
        self.assertEqual(row["cost"]["wall_clock"], {"status": "known", "seconds": 0})
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 0)
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "skipped")

    def test_a_skipped_pass_needs_no_record_and_reads_no_usage(self):
        self.ok(500, "gate", "--skip-reason", "budget spent", before=None, usage=None)
        self.assertEqual(self.only_row()["cost"]["usage_delta"]["delta"], 0)

    def test_a_skipped_pass_is_not_a_clean_pass_in_the_report(self):
        self.ok(500, "gate", "--skip-reason", "capped", before=None)
        put(self.skills, 501, "gate", STARTED, COMPLETED, OUT_CLEAN)
        self.ok(501, "gate", usage=12)
        r = subprocess.run([sys.executable, str(SCRIPT), "report", "--ledger", str(self.ledger), "--format", "json"],
                           capture_output=True, text=True, env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        (t,) = [t for t in json.loads(r.stdout)["types"] if t["type"] == "codex-gate"]
        self.assertEqual((t["rows"], t["clean_rows"], t["skipped_rows"], t["unknown_finding_rows"]), (2, 1, 1, 0))

    def test_an_empty_reason_is_refused(self):
        r = self.skip(500, "gate", "  ", before=None)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(self.ledger.exists())


class RefusalTest(CodexAppendCase):
    def test_usage_and_skip_flags_are_for_codex_types(self):
        for flags in (["--usage-before", "1"], ["--skip-reason", "x"]):
            r = run_append("--repo", "skills", "--ticket", 500, "--type", "spec", "--cache", self.cache,
                           "--ledger", self.ledger, *flags, home=self.home)
            self.assertEqual(r.returncode, 2)
            self.assertIn("codex", r.stderr)

    def test_mutation_flags_are_refused_on_a_codex_type(self):
        r = self.append(500, "gate", "--mutation-id", "m1", "--outcome", "red", "--seconds", 3)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
