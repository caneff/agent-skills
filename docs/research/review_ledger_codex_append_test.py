#!/usr/bin/env python3
"""Tests for the Codex rows the controller writes at merge (#1269): `append --type codex-<phase>`
and `harvest`, both reading the usage change from the two live readings the pass's record carries
(`usage_before`, `usage_after`, as `codex-usage-gate.py --percent` prints them). Every test runs the
command line; HOME is a temp dir, so no default path reaches the real ~/.cache."""
import json
import unittest

from review_ledger_codex_test import OUT_CLEAN, OUT_REFUSED, OUT_TWO, put
from review_ledger_test import Case, run

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

    def harvest(self):
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tmp, "--ledger", self.ledger,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)


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
        for phase in ("gate", "second"):
            self.record(500, phase, f"1 {W1}", f"2 {W1}")
            self.ok(500, phase)
        self.assertEqual(sorted(r["type"] for r in self.rows().values()), ["codex-gate", "codex-second"])

    def test_the_retired_third_phase_is_refused_by_name(self):
        """#1360: the second pass is final, so a stale controller's third row is refused, not written."""
        self.record(500, "third", f"1 {W1}", f"2 {W1}")
        for extra in ((), ("--skip-reason", "usage capped"), ("--refusal", "stale")):
            r = self.append(500, "third", *extra)
            self.assertNotEqual(r.returncode, 0, extra)
            self.assertIn("codex-third is retired", r.stderr)
            self.assertIn("append no row for it", r.stderr)
        self.assertFalse(self.ledger.exists())

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
        self.harvest()
        self.assertEqual(self.only_row(), appended)

    def test_a_harvest_after_the_record_is_pruned_keeps_the_appended_row(self):
        # #1304: append, harvest, the 14-day prune takes the record, harvest again.
        self.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        self.record(501)  # a second record, so the cache is not empty once ticket 500's is gone
        self.ok(500, "gate")
        appended = self.rows()["skills/500/codex-gate/1/codex-adversarial-500-gate"]
        self.harvest()
        for suffix in (".json", ".out"):
            (self.skills / f"codex-adversarial-500-gate{suffix}").unlink()
        self.harvest()
        self.assertEqual(self.rows().get("skills/500/codex-gate/1/codex-adversarial-500-gate"), appended)

    def test_a_harvest_after_the_out_is_pruned_keeps_the_known_findings(self):
        # The controller writes the .out seconds before the .json, so the prune can take it first.
        self.record(500, before=f"10 {W1}", after=f"12 {W1}", out=OUT_TWO)
        self.ok(500, "gate")
        appended = self.only_row()
        (self.skills / "codex-adversarial-500-gate.out").unlink()
        self.harvest()
        row = self.only_row()
        self.assertEqual((row["findings"], row["status"]["fields"]["findings"]),
                         (appended["findings"], appended["status"]["fields"]["findings"]))

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
        self.harvest()
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


class AuditTest(CodexAppendCase):
    """`append --type codex-audit` (#1361): the weekly audit's one run over the PRs that skipped the gate."""
    PRS, RANGE = [101, 104, 107], "aaa..bbb"

    def audit_record(self, before=f"10 {W1}", after=f"14 {W1}", out=OUT_TWO, status=0, name="2026-10-09",
                     drop=(), **fields):
        """An audit record at its own path per `name`; `fields` replace its values, `drop` removes keys."""
        rec = {"prs": self.PRS, "range": self.RANGE, "status": status, "started": STARTED, "completed": COMPLETED,
               "usage_before": before, "usage_after": after, **fields}
        for key in drop:
            rec.pop(key)
        path = self.skills / f"codex-audit-{name}.json"
        self.skills.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec) + "\n")
        if out is not None:
            path.with_suffix(".out").write_text(out)
        return path

    def audit(self, *extra):
        return run("append", "--repo", "skills", "--type", "codex-audit", "--ledger", self.ledger, *extra,
                   home=self.home)

    def report(self):
        r = run("report", "--ledger", self.ledger, "--format", "json", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {t["type"]: t for t in json.loads(r.stdout)["types"]}

    def test_an_audit_row_holds_its_prs_range_usage_change_and_findings(self):
        r = self.audit("--record", self.audit_record())
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.only_row()
        self.assertEqual((row["type"], row["prs"], row["range"]), ("codex-audit", self.PRS, self.RANGE))
        self.assertEqual(row["cost"]["usage_delta"], {"status": "known", "before": 10.0, "after": 14.0, "delta": 4.0})
        self.assertEqual(row["cost"]["wall_clock"]["seconds"], 150)
        self.assertEqual([f["severity"] for f in row["findings"]], ["high", "medium"])
        self.assertEqual(row["status"]["fields"]["findings"], {"status": "known"})

    def test_the_report_counts_an_audit_under_its_own_audit_column(self):
        self.audit("--record", self.audit_record())
        self.record(500, before=f"1 {W1}", after=f"2 {W1}")
        self.ok(500, "gate")
        types = self.report()
        self.assertEqual((types["codex-audit"]["rows"], types["codex-audit"]["audited_prs"]), (1, 3))
        self.assertEqual(types["codex-audit"]["usage_percent"], 4.0)
        self.assertIsNone(types["codex-gate"]["audited_prs"])
        md = run("report", "--ledger", self.ledger, home=self.home).stdout
        header = [c.strip() for c in md.splitlines()[0].strip("|").split("|")]
        (audit_line,) = [line for line in md.splitlines() if line.startswith("| codex-audit |")]
        cells = [c.strip() for c in audit_line.strip("|").split("|")]
        self.assertEqual(cells[header.index("audited PRs")], "3")

    def test_usage_change_follows_the_two_reading_rule(self):
        for before, after, why in ((None, f"14 {W1}", "before reading missing"),
                                   (f"10 {W1}", f"1 {W2}", "different windows"),
                                   (f"10 {W1}", f"9 {W1}", "usage fell")):
            self.audit("--record", self.audit_record(before=before, after=after))
            delta = self.only_row()["cost"]["usage_delta"]
            self.assertEqual(delta["status"], "unknown", why)
            self.assertIn(why, delta["reason"])
            self.ledger.unlink()

    def test_an_audit_that_failed_is_a_refusal_with_no_findings(self):
        self.audit("--record", self.audit_record(status=1, out=OUT_REFUSED))
        row = self.only_row()
        self.assertEqual((row["findings"], row["status"]["fields"]["findings"]["status"]), ([], "refused"))
        self.audit("--record", self.audit_record(), "--refusal", "range moved")
        row = self.only_row()
        self.assertEqual((row["findings"], row["refusal"]), ([], "range moved"))
        self.assertEqual(row["cost"]["usage_delta"]["delta"], 4.0)
        self.assertEqual(self.report()["codex-audit"]["refused_rows"], 1)

    def test_an_audit_record_reads_its_status_as_a_gate_record_does(self):
        """One record-to-status rule for both Codex row kinds: a failed run's refusal quotes the Codex
        error line, and a status that is not an integer is never a clean run."""
        self.audit("--record", self.audit_record(status=1, out=OUT_REFUSED))
        self.assertEqual(self.only_row()["status"]["fields"]["findings"]["reason"],
                         "exit status 1: You've hit your usage limit. Try again at Oct 3rd.")
        self.ledger.unlink()
        self.audit("--record", self.audit_record(status=False))
        row = self.only_row()
        self.assertEqual((row["findings"], row["status"]["fields"]["findings"]["status"]), ([], "refused"))

    def test_an_unreadable_out_is_unknown_never_a_clean_audit(self):
        self.audit("--record", self.audit_record(out=None))
        self.assertEqual(self.only_row()["status"]["fields"]["findings"]["status"], "unknown")
        self.assertEqual(self.report()["codex-audit"]["clean_rows"], 0)

    def test_an_audit_not_launched_is_a_skipped_row(self):
        r = self.audit("--skip-reason", "ceiling")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.only_row()
        self.assertEqual((row["type"], row["skip_reason"], row["cost"]["usage_delta"]["delta"]),
                         ("codex-audit", "ceiling", 0))
        self.assertEqual(self.report()["codex-audit"]["skipped_rows"], 1)

    def test_a_later_harvest_keeps_the_audit_row(self):
        self.audit("--record", self.audit_record())
        self.record(500, before=f"1 {W1}", after=f"2 {W1}")  # harvest refuses a cache with no record at all
        self.harvest()
        (row,) = [r for r in self.rows().values() if r["type"] == "codex-audit"]
        self.assertEqual(row["prs"], self.PRS)

    def test_a_bad_audit_append_is_refused_by_its_own_guard_and_writes_nothing(self):
        good = self.audit_record()
        cases = [
            (["--record", good, "--ticket", "500"], "takes no --ticket or --cache"),
            (["--record", good, "--cache", self.cache], "takes no --ticket or --cache"),
            (["--record", good, "--round", "2"], "is round 1"),
            (["--record", good, "--seconds", "3"], "are not for an audit row"),
            ([], "exactly one of --record and --skip-reason"),
            (["--record", good, "--skip-reason", "x"], "exactly one of --record and --skip-reason"),
            (["--skip-reason", " "], "non-empty reason"),
            (["--record", self.tmp / "absent.json"], "absent.json"),
            (["--record", self.audit_record(name="prs-not-ints", prs=["101"])], "needs `prs`"),
            (["--record", self.audit_record(name="prs-missing", drop=("prs",))], "needs `prs`"),
            (["--record", self.audit_record(name="range-not-str", range=7)], "needs `prs`"),
            (["--record", good, "--refusal", " "], "--refusal needs the reason"),
        ]
        for extra, why in cases:
            r = self.audit(*extra)
            self.assertEqual(r.returncode, 2, extra)
            self.assertIn(f"codex-audit: ", r.stderr, extra)
            self.assertIn(why, r.stderr, extra)
        self.assertFalse(self.ledger.exists())

    def test_a_record_with_no_status_is_refused_saying_so(self):
        self.audit("--record", self.audit_record(drop=("status",)))
        fstatus = self.only_row()["status"]["fields"]["findings"]
        self.assertEqual(fstatus["status"], "refused")
        self.assertIn("has no status", fstatus["reason"])

    def test_a_pass_type_still_needs_its_ticket_and_takes_no_record(self):
        for extra, why in ((["--type", "codex-gate", "--skip-reason", "size"], "codex-gate needs --ticket"),
                           (["--type", "spec", "--cache", self.cache], "spec needs --ticket"),
                           (["--type", "codex-gate", "--ticket", "500", "--skip-reason", "size",
                             "--record", self.audit_record()], "--record is for codex-audit, not codex-gate")):
            r = run("append", "--repo", "skills", "--ledger", self.ledger, *extra, home=self.home)
            self.assertEqual(r.returncode, 2, extra)
            self.assertIn(why, r.stderr)
        self.assertFalse(self.ledger.exists())

if __name__ == "__main__":
    unittest.main()
