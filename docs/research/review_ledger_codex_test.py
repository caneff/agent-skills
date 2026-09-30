#!/usr/bin/env python3
"""Tests for the Codex rows of `review_ledger.py` (#1267): `harvest` fed
`codex-adversarial-<n>-<phase>.{json,out}` records, and the Codex columns of `report`.
Every test runs the command line on a fixture tree; HOME is a temp dir, so no default
path reaches the real ~/.cache or ~/.claude."""
import json
import unittest

from review_ledger_test import Case, finding, run, write_jsonl

OUT_TWO = """[codex] Starting Codex task thread.
# Codex Adversarial Review

Target: branch diff against origin/main
Verdict: needs-attention

No ship.

Findings:
- [high] Guard breaks first pushes (flow/guard.sh:34-42)
  Body of the first finding (with parens).
  Recommendation: fix it.
- [medium] Prefix match swallows a conflict (flow/install.sh:70)
  Body.

Next steps:
- Fix both.
"""
OUT_CLEAN = """# Codex Adversarial Review

Verdict: approve

Ship.

No material findings.
"""
OUT_REFUSED = """[codex] Turn started (x).
[codex] Codex error: You've hit your usage limit. Try again at Oct 3rd.
[codex] Turn failed.
# Codex Adversarial Review

Codex did not return valid structured JSON.

- Parse error: You've hit your usage limit.
"""
OUT_UNPARSED = """# Codex Adversarial Review

Verdict: needs-attention

Findings:
  something the parser cannot read
"""


def record(ticket, phase, started, completed, status=0):
    return {"ticket": ticket, "phase": phase, "status": status, "launch_sha": "a", "completion_sha": "a",
            "body_sha256": "b", "started": started, "completed": completed}


def put(repo_dir, ticket, phase, started, completed, out, status=0):
    stem = repo_dir / f"codex-adversarial-{ticket}-{phase}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".json").write_text(json.dumps(record(ticket, phase, started, completed, status)) + "\n")
    if out is not None:
        stem.with_suffix(".out").write_text(out)


def build_codex_cache(root):
    skills = root / "skills"
    # 200: all three phases. Gate: two findings, joined to dispositions by number.
    put(skills, 200, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:02:30-04:00", OUT_TWO)
    put(skills, 200, "second", "2026-09-22T09:10:00-04:00", "2026-09-22T09:11:00-04:00", OUT_TWO)
    put(skills, 200, "third", "2026-09-22T09:20:00-04:00", "2026-09-22T09:20:45-04:00", OUT_CLEAN)
    write_jsonl(skills / "dispositions-200.jsonl", [
        {"id": "codex-gate-1", "outcome": "fixed", "sha": "abc"},
        {"id": "codex-gate-2", "outcome": "leftover", "file": "flow/install.sh", "title": "t",
         "severity": "medium", "text": "kept"},
        {"id": "codex-second-H1", "outcome": "disputed", "reason": "unreachable"},
        {"id": "codex-second-M1", "outcome": "filed", "ticket": 9},
        {"id": "codex-third-9", "outcome": "fixed", "sha": "z"},
    ])
    # 201: refused at the usage limit.
    put(skills, 201, "gate", "2026-09-27T14:10:35-04:00", "2026-09-27T14:10:38-04:00", OUT_REFUSED, status=1)
    # 202: findings the parser cannot read; 203: a record with no .out at all.
    put(skills, 202, "gate", "2026-09-22T10:00:00-04:00", "2026-09-22T10:01:00-04:00", OUT_UNPARSED)
    put(skills, 203, "gate", "2026-09-22T11:00:00-04:00", "2026-09-22T11:01:00-04:00", None)
    # 204: a retried gate, an early launch (not one of the three types), and a record
    # whose timestamps do not parse.
    put(skills, 204, "gate-retry", "2026-09-22T12:00:00-04:00", "2026-09-22T12:00:10-04:00", OUT_CLEAN)
    put(skills, 204, "early", "2026-09-22T12:10:00-04:00", "2026-09-22T12:10:10-04:00", OUT_CLEAN)
    put(skills, 205, "gate", "not a time", "2026-09-22T12:10:10-04:00", OUT_CLEAN)
    # 206: a Claude finding matching Codex's first finding: shared credit.
    write_jsonl(skills / "findings-spec-206.jsonl",
                [finding("P1", "hard", "flow/guard.sh", "guard breaks first pushes", axis="spec")])
    write_jsonl(skills / "dispositions-206.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"},
                                                   {"id": "codex-gate-1", "outcome": "fixed", "sha": "f"}])
    put(skills, 206, "gate", "2026-09-22T13:00:00-04:00", "2026-09-22T13:01:00-04:00", OUT_TWO)
    # 207: a dispositions line for a Codex pass that has no record in this ticket: stays an orphan
    # although other tickets join the same `codex-gate-1` id.
    write_jsonl(skills / "dispositions-207.jsonl", [{"id": "codex-gate-1", "outcome": "fixed", "sha": "q"}])
    # A scratch directory is not a review directory.
    put(root / "scratch-9", 999, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_TWO)
    # A repo whose cache holds only Codex records.
    put(root / "other", 300, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)


class CodexHarvestTest(Case):
    def setUp(self):
        super().setUp()
        self.cache = self.tmp / "cache"
        build_codex_cache(self.cache)
        self.harvest(self.cache)
        self.all = self.rows()

    def row(self, ticket, phase, repo="skills", stem=None):
        return self.all[f"{repo}/{ticket}/codex-{phase}/1/{stem or f'codex-adversarial-{ticket}-{phase}'}"]

    def test_each_phase_is_its_own_typed_row_with_its_wall_clock(self):
        for phase, seconds in (("gate", 150), ("second", 60), ("third", 45)):
            r = self.row(200, phase)
            self.assertEqual(r["type"], f"codex-{phase}")
            self.assertEqual(r["cost"]["wall_clock"]["status"], "known")
            self.assertEqual(r["cost"]["wall_clock"]["seconds"], seconds)

    def test_findings_keep_severity_as_written_and_name_the_file(self):
        fs = self.row(200, "gate")["findings"]
        self.assertEqual([(f["severity"], f["file"]) for f in fs],
                         [("high", "flow/guard.sh"), ("medium", "flow/install.sh")])
        self.assertEqual(fs[0]["title"], "Guard breaks first pushes")

    def test_outcomes_come_from_codex_ids_in_the_dispositions_sidecar(self):
        gate = self.row(200, "gate")["findings"]
        self.assertEqual([f["outcome"] for f in gate], ["fixed", "leftover"])
        self.assertTrue(all(f["outcome_status"]["status"] == "known" for f in gate))
        self.assertIn("dispositions-200.jsonl", " ".join(self.row(200, "gate")["status"]["sources"]))

    def test_a_severity_letter_label_joins_the_nth_finding_of_that_severity(self):
        second = self.row(200, "second")["findings"]
        self.assertEqual([f["outcome"] for f in second], ["disputed", "filed"])

    def test_a_finding_with_no_disposition_is_unknown_with_the_reason(self):
        fs = self.row(206, "gate")["findings"]
        self.assertEqual(fs[1]["outcome"], "unknown")
        self.assertIn("codex-gate-2", fs[1]["outcome_status"]["reason"])
        clean_third = self.row(200, "third")
        self.assertEqual(clean_third["findings"], [])
        self.assertEqual(clean_third["status"]["fields"]["findings"]["status"], "known")

    def test_usage_change_is_unknown_on_a_backfilled_row(self):
        self.assertEqual(self.row(200, "gate")["cost"]["usage_delta"]["status"], "unknown")
        self.assertEqual(self.row(200, "gate")["cost"]["tokens"]["status"], "not-applicable")

    def test_a_refused_record_is_a_refusal_row_with_no_findings_never_a_clean_pass(self):
        r = self.row(201, "gate")
        self.assertEqual(r["findings"], [])
        self.assertEqual(r["status"]["fields"]["findings"]["status"], "refused")
        self.assertIn("usage limit", r["status"]["fields"]["findings"]["reason"])
        self.assertEqual(r["exit_status"], 1)
        self.assertEqual(r["cost"]["wall_clock"]["seconds"], 3)

    def test_findings_that_cannot_be_parsed_are_unknown_not_empty(self):
        r = self.row(202, "gate")
        self.assertEqual(r["status"]["fields"]["findings"]["status"], "unknown")
        self.assertEqual(r["findings"], [])

    def test_a_record_without_its_out_file_is_unknown_findings(self):
        r = self.row(203, "gate")
        self.assertEqual(r["status"]["fields"]["findings"]["status"], "unknown")
        self.assertIn("no .out", r["status"]["fields"]["findings"]["reason"])

    def test_unparseable_timestamps_are_unknown_wall_clock_never_zero(self):
        c = self.row(205, "gate")["cost"]["wall_clock"]
        self.assertEqual(c["status"], "unknown")
        self.assertNotIn("seconds", c)

    def test_a_gate_retry_is_a_gate_row_and_the_mapping_is_listed(self):
        r = self.row(204, "gate", stem="codex-adversarial-204-gate-retry")
        self.assertEqual(r["type"], "codex-gate")
        self.assertIn("gate-retry", self.review.read_text())

    def test_a_phase_with_no_type_is_listed_not_harvested(self):
        self.assertFalse(any("204-early" in rid for rid in self.all))
        section = self.review.read_text().split("## Sidecars not harvested")[1].split("\n## ")[0]
        self.assertIn("codex-adversarial-204-early.json", section)

    def test_a_scratch_directory_and_a_codex_only_repo(self):
        self.assertFalse(any("/999/" in rid for rid in self.all))
        self.assertIn("other/300/codex-gate/1/codex-adversarial-300-gate", self.all)

    def test_a_finding_raised_by_codex_and_a_claude_axis_is_shared_on_both(self):
        codex = self.row(206, "gate")["findings"][0]
        spec = self.all["skills/206/spec/1/findings-spec-206"]["findings"][0]
        self.assertEqual((codex["overlap"], codex["k"]), ("shared", 2))
        self.assertEqual((spec["overlap"], spec["k"]), ("shared", 2))

    def test_codex_passes_of_one_ticket_do_not_share_credit_with_each_other(self):
        for phase in ("gate", "second"):
            for f in self.row(200, phase)["findings"]:
                self.assertEqual((f["overlap"], f["k"]), ("unique", 1))

    def test_another_tickets_line_with_a_joined_id_stays_an_orphan(self):
        section = self.review.read_text().split("## Dispositions with no finding")[1].split("\n## ")[0]
        self.assertIn("#207 `codex-gate-1`", section)

    def test_the_codex_dispositions_are_no_longer_orphans(self):
        section = self.review.read_text().split("## Dispositions with no finding")[1].split("\n## ")[0]
        self.assertNotIn("#200 `codex-gate-1`", section)
        self.assertNotIn("#200 `codex-second-H1`", section)
        self.assertIn("#200 `codex-third-9`", section)

    def test_harvesting_twice_gives_one_row_per_record(self):
        before = self.ledger.read_text()
        self.harvest(self.cache)
        self.assertEqual(self.ledger.read_text(), before)


ONE_HIGH = """Verdict: needs-attention

Findings:
- [high] One real finding (flow/a.sh:1)
  Body.

Next steps:
- Fix.
"""


class CodexGuardTest(Case):
    """Small caches, one per guard: each ticket here exists to trip exactly one."""

    def cache_rows(self, build):
        cache = self.tmp / "cache"
        build(cache)
        self.harvest(cache)
        return self.rows()

    def test_two_labels_naming_one_finding_leave_it_unknown(self):
        def build(root):
            put(root / "skills", 207, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-207.jsonl", [
                {"id": "codex-gate-1", "outcome": "fixed", "sha": "a"},
                {"id": "codex-gate-H1", "outcome": "disputed", "reason": "no"}])
        f = self.cache_rows(build)["skills/207/codex-gate/1/codex-adversarial-207-gate"]["findings"][0]
        self.assertEqual(f["outcome"], "unknown")
        self.assertIn("both name this finding", f["outcome_status"]["reason"])

    def test_a_record_that_disagrees_with_its_file_name_is_skipped_and_listed(self):
        def build(root):
            skills = root / "skills"
            put(skills, 208, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
            (skills / "codex-adversarial-208-gate.json").write_text(
                json.dumps(record(999, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00")))
            put(skills, 209, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
        rows = self.cache_rows(build)
        self.assertFalse(any("/208/" in rid or "/999/" in rid for rid in rows))
        self.assertIn("codex-adversarial-208-gate.json: record is unreadable or disagrees",
                      self.review.read_text())

    def test_a_record_completed_before_it_started_has_unknown_wall_clock(self):
        def build(root):
            put(root / "skills", 209, "gate", "2026-09-22T09:05:00-04:00", "2026-09-22T09:00:00-04:00", OUT_CLEAN)
        wall = self.cache_rows(build)["skills/209/codex-gate/1/codex-adversarial-209-gate"]["cost"]["wall_clock"]
        self.assertEqual(wall["status"], "unknown")
        self.assertNotIn("seconds", wall)

    def test_a_gate_and_its_retry_do_not_both_take_one_disposition(self):
        def build(root):
            for phase in ("gate", "gate-retry"):
                put(root / "skills", 210, phase, "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-210.jsonl", [{"id": "codex-gate-1", "outcome": "fixed", "sha": "a"}])
        rows = self.cache_rows(build)
        gate = rows["skills/210/codex-gate/1/codex-adversarial-210-gate"]["findings"][0]
        retry = rows["skills/210/codex-gate/1/codex-adversarial-210-gate-retry"]["findings"][0]
        self.assertEqual(gate["outcome"], "fixed")
        self.assertEqual(retry["outcome"], "unknown")
        self.assertIn("already credits", retry["outcome_status"]["reason"])

    def test_the_same_record_under_the_alias_directories_gives_two_rows(self):
        def build(root):
            for d in ("skills", "agent-skills"):
                put(root / d, 211, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
        rows = [rid for rid in self.cache_rows(build) if "/211/codex-gate/" in rid]
        self.assertEqual(len(rows), 2)


class CodexReportTest(Case):
    def report(self, *extra):
        cache = self.tmp / "cache"
        build_codex_cache(cache)
        self.harvest(cache)
        out = run("report", "--ledger", self.ledger, "--format", "json", *extra, home=self.home)
        self.assertEqual(out.returncode, 0, out.stderr)
        return {t["type"]: t for t in json.loads(out.stdout)["types"]}

    def test_the_three_phases_are_separate_table_rows(self):
        types = self.report()
        for phase in ("codex-gate", "codex-second", "codex-third"):
            self.assertIn(phase, types)

    def test_codex_value_uses_the_codex_weights(self):
        # ticket 200 gate: high fixed = 3, medium leftover = 0. 206 gate: high fixed shared with spec = 3/2,
        # medium unknown = 0. Gate rows also hold 204's clean retry and 300's clean pass.
        gate = self.report()["codex-gate"]
        self.assertEqual(gate["value"], 4.5)
        self.assertEqual(self.report("--weights", self.write_weights())["codex-gate"]["value"], 9.0)

    def write_weights(self):
        p = self.tmp / "weights.json"
        p.write_text(json.dumps({"high": 6, "medium": 2, "low": 1, "hard": 3, "judgement": 1}))
        return p

    def test_a_refused_row_is_counted_as_refused_and_never_as_a_clean_pass(self):
        gate = self.report()["codex-gate"]
        self.assertEqual(gate["refused_rows"], 1)
        # 201 (refused), 202 and 203 have refused or unknown findings: none is a known-empty pass.
        # The clean ones are 204's retry, 205 and 300.
        self.assertEqual(gate["clean_rows"], 3)
        self.assertEqual(self.report()["codex-third"]["refused_rows"], 0)

    def test_a_refused_row_is_not_an_unknown_findings_row_and_a_claude_type_has_no_clean_column(self):
        types = self.report()
        # 202 (unparsed) and 203 (no .out) only: the refused 201 is counted in `refused_rows`, once.
        self.assertEqual(types["codex-gate"]["unknown_finding_rows"], 2)
        self.assertIsNone(types["spec"]["clean_rows"])

    def test_codex_cost_is_wall_clock_with_no_tokens_or_dollars(self):
        gate = self.report()["codex-gate"]
        self.assertIsNone(gate["tokens"])
        self.assertIsNone(gate["dollars"])
        self.assertEqual(gate["unknown_cost_rows"], 1)  # 205's unparseable timestamps
        self.assertGreater(gate["wall_clock_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
