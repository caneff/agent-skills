"""Tests for the Codex rows of `review_ledger.py` (#1267): `harvest` fed
`codex-adversarial-<n>-<phase>.{json,out}` records, and the Codex columns of `report`.
Every test runs the command line on a fixture tree; HOME is a temp dir, so no default
path reaches the real ~/.cache or ~/.claude."""
import json

import pytest

from review_ledger_support import OUT_CLEAN, build_codex_cache, put, record, section, write_jsonl

ONE_HIGH = """Verdict: needs-attention

Findings:
- [high] One real finding (flow/a.sh:1)
  Body.

Next steps:
- Fix.
"""


class TestCodexHarvest:
    @pytest.fixture
    def env(self, env):
        env.cache = env.tmp / "cache"
        build_codex_cache(env.cache)
        env.harvest(env.cache)
        env.all = env.rows()
        return env

    def row(self, env, ticket, phase, repo="skills", stem=None):
        return env.all[f"{repo}/{ticket}/codex-{phase}/1/{stem or f'codex-adversarial-{ticket}-{phase}'}"]

    @pytest.mark.parametrize("phase, seconds", [("gate", 150), ("second", 60), ("third", 45)])
    def test_each_phase_is_its_own_typed_row_with_its_wall_clock(self, env, phase, seconds):
        r = self.row(env, 200, phase)
        assert r["type"] == f"codex-{phase}"
        assert r["cost"]["wall_clock"]["status"] == "known"
        assert r["cost"]["wall_clock"]["seconds"] == seconds

    def test_findings_keep_severity_as_written_and_name_the_file(self, env):
        fs = self.row(env, 200, "gate")["findings"]
        assert [(f["severity"], f["file"]) for f in fs] == [("high", "flow/guard.sh"), ("medium", "flow/install.sh")]
        assert fs[0]["title"] == "Guard breaks first pushes"

    def test_outcomes_come_from_codex_ids_in_the_dispositions_sidecar(self, env):
        gate = self.row(env, 200, "gate")["findings"]
        assert [f["outcome"] for f in gate] == ["fixed", "leftover"]
        assert all(f["outcome_status"]["status"] == "known" for f in gate)
        assert "dispositions-200.jsonl" in " ".join(self.row(env, 200, "gate")["status"]["sources"])

    def test_a_severity_letter_label_joins_the_nth_finding_of_that_severity(self, env):
        second = self.row(env, 200, "second")["findings"]
        assert [f["outcome"] for f in second] == ["disputed", "filed"]

    def test_a_finding_with_no_disposition_is_unknown_with_the_reason(self, env):
        fs = self.row(env, 206, "gate")["findings"]
        assert fs[1]["outcome"] == "unknown"
        assert "codex-gate-2" in fs[1]["outcome_status"]["reason"]
        clean_third = self.row(env, 200, "third")
        assert clean_third["findings"] == []
        assert clean_third["status"]["fields"]["findings"]["status"] == "known"

    def test_usage_change_is_unknown_on_a_backfilled_row(self, env):
        assert self.row(env, 200, "gate")["cost"]["usage_delta"]["status"] == "unknown"
        assert self.row(env, 200, "gate")["cost"]["tokens"]["status"] == "not-applicable"

    def test_a_refused_record_is_a_refusal_row_with_no_findings_never_a_clean_pass(self, env):
        r = self.row(env, 201, "gate")
        assert r["findings"] == []
        assert r["status"]["fields"]["findings"]["status"] == "refused"
        assert "usage limit" in r["status"]["fields"]["findings"]["reason"]
        assert r["exit_status"] == 1
        assert r["cost"]["wall_clock"]["seconds"] == 3

    def test_findings_that_cannot_be_parsed_are_unknown_not_empty(self, env):
        r = self.row(env, 202, "gate")
        assert r["status"]["fields"]["findings"]["status"] == "unknown"
        assert r["findings"] == []

    def test_a_record_without_its_out_file_is_unknown_findings(self, env):
        r = self.row(env, 203, "gate")
        assert r["status"]["fields"]["findings"]["status"] == "unknown"
        assert "no .out" in r["status"]["fields"]["findings"]["reason"]

    def test_unparseable_timestamps_are_unknown_wall_clock_never_zero(self, env):
        c = self.row(env, 205, "gate")["cost"]["wall_clock"]
        assert c["status"] == "unknown"
        assert "seconds" not in c

    def test_a_gate_retry_is_a_gate_row_and_the_mapping_is_listed(self, env):
        r = self.row(env, 204, "gate", stem="codex-adversarial-204-gate-retry")
        assert r["type"] == "codex-gate"
        assert "gate-retry" in env.review.read_text()

    def test_a_phase_with_no_type_is_listed_not_harvested(self, env):
        assert not any("204-early" in rid for rid in env.all)
        assert "codex-adversarial-204-early.json" in section(env.review.read_text(), "Sidecars not harvested")

    def test_a_scratch_directory_and_a_codex_only_repo(self, env):
        assert not any("/999/" in rid for rid in env.all)
        assert "other/300/codex-gate/1/codex-adversarial-300-gate" in env.all

    def test_a_finding_raised_by_codex_and_a_claude_axis_is_shared_on_both(self, env):
        codex = self.row(env, 206, "gate")["findings"][0]
        spec = env.all["skills/206/spec/1/findings-spec-206"]["findings"][0]
        assert (codex["overlap"], codex["k"]) == ("shared", 2)
        assert (spec["overlap"], spec["k"]) == ("shared", 2)

    @pytest.mark.parametrize("phase", ["gate", "second"])
    def test_codex_passes_of_one_ticket_do_not_share_credit_with_each_other(self, env, phase):
        for f in self.row(env, 200, phase)["findings"]:
            assert (f["overlap"], f["k"]) == ("unique", 1)

    def test_another_tickets_line_with_a_joined_id_stays_an_orphan(self, env):
        assert "#207 `codex-gate-1`" in section(env.review.read_text(), "Dispositions with no finding")

    def test_the_codex_dispositions_are_no_longer_orphans(self, env):
        text = section(env.review.read_text(), "Dispositions with no finding")
        assert "#200 `codex-gate-1`" not in text
        assert "#200 `codex-second-H1`" not in text
        assert "#200 `codex-third-9`" in text

    def test_harvesting_twice_gives_one_row_per_record(self, env):
        before = env.ledger.read_text()
        env.harvest(env.cache)
        assert env.ledger.read_text() == before


class TestCodexGuard:
    """Small caches, one per guard: each ticket here exists to trip exactly one."""

    def cache_rows(self, env, build):
        cache = env.tmp / "cache"
        build(cache)
        env.harvest(cache)
        return env.rows()

    def test_two_labels_naming_one_finding_leave_it_unknown(self, env):
        def build(root):
            put(root / "skills", 207, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-207.jsonl", [
                {"id": "codex-gate-1", "outcome": "fixed", "sha": "a"},
                {"id": "codex-gate-H1", "outcome": "disputed", "reason": "no"}])
        f = self.cache_rows(env, build)["skills/207/codex-gate/1/codex-adversarial-207-gate"]["findings"][0]
        assert f["outcome"] == "unknown"
        assert "both name this finding" in f["outcome_status"]["reason"]

    def test_a_record_that_disagrees_with_its_file_name_is_skipped_and_listed(self, env):
        def build(root):
            skills = root / "skills"
            put(skills, 208, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
            (skills / "codex-adversarial-208-gate.json").write_text(
                json.dumps(record(999, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00")))
            put(skills, 209, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
        rows = self.cache_rows(env, build)
        assert not any("/208/" in rid or "/999/" in rid for rid in rows)
        assert "codex-adversarial-208-gate.json: record is unreadable or disagrees" in env.review.read_text()

    def test_a_record_completed_before_it_started_has_unknown_wall_clock(self, env):
        def build(root):
            put(root / "skills", 209, "gate", "2026-09-22T09:05:00-04:00", "2026-09-22T09:00:00-04:00", OUT_CLEAN)
        wall = self.cache_rows(env, build)["skills/209/codex-gate/1/codex-adversarial-209-gate"]["cost"]["wall_clock"]
        assert wall["status"] == "unknown"
        assert "seconds" not in wall

    def split(self, env, *halves):
        def build(root):
            put(root / "skills", 211, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-211.jsonl", list(halves))
        return self.cache_rows(env, build)["skills/211/codex-gate/1/codex-adversarial-211-gate"]["findings"][0]

    def test_a_split_id_whose_halves_differ_joins_its_finding_as_a_partial_fix(self, env):
        f = self.split(env, {"id": "codex-gate-1a", "outcome": "fixed", "sha": "a"},
                       {"id": "codex-gate-1b", "outcome": "leftover", "text": "the race stays"})
        assert (f["outcome"], f["partial"], f["outcome_status"]) == ("fixed", True, {"status": "known"})
        assert "codex-gate-1" not in section(env.review.read_text(), "Dispositions with no finding")

    def test_a_valued_half_beside_an_unreadable_half_is_unknown_and_listed_unmapped(self, env):
        # #1406 C3: half the ruling unread is not a known partial fix.
        f = self.split(env, {"id": "codex-gate-1a", "outcome": "fixed", "sha": "a"},
                       {"id": "codex-gate-1b", "outcome": "bogus-word"})
        assert (f["outcome"], f["partial"]) == ("unknown", False)
        assert "codex-gate-1b" in f["outcome_status"]["reason"]
        assert "bogus-word" in f["outcome_status"]["reason"]
        assert "bogus-word" in section(env.review.read_text(), "Unmapped values")

    def test_a_split_id_whose_halves_agree_takes_their_outcome(self, env):
        f = self.split(env, {"id": "codex-gate-H1a", "outcome": "disputed", "reason": "no"},
                       {"id": "codex-gate-H1b", "outcome": "disputed", "reason": "no"})
        assert (f["outcome"], f["partial"]) == ("disputed", False)

    def test_a_split_id_with_no_valued_half_is_unknown(self, env):
        f = self.split(env, {"id": "codex-gate-1a", "outcome": "leftover", "text": "x"},
                       {"id": "codex-gate-1b", "outcome": "disputed", "reason": "no"})
        assert f["outcome"] == "unknown"
        assert "codex-gate-1a and codex-gate-1b" in f["outcome_status"]["reason"]

    def test_a_split_id_with_a_missing_half_is_unknown(self, env):
        f = self.split(env, {"id": "codex-gate-1a", "outcome": "fixed", "sha": "a"})
        assert f["outcome"] == "unknown"
        assert "codex-gate-1b" in f["outcome_status"]["reason"]

    def test_a_codex_rows_own_mappings_name_its_phase_label_and_outcome_mappings(self, env):
        def build(root):
            put(root / "skills", 212, "gate-retry", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00",
                ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-212.jsonl", [
                {"id": "codex-gate-H1", "outcome": "partial", "sha": "a"}])
        row = self.cache_rows(env, build)["skills/212/codex-gate/1/codex-adversarial-212-gate-retry"]
        assert row["status"]["mappings"] == [
            {"from": "phase gate-retry", "to": "codex-gate"},
            {"from": "codex label H<k>", "to": "k-th finding of that severity"},
            {"from": "partial", "to": "fixed+partial"}]

    def test_a_gate_and_its_retry_do_not_both_take_one_disposition(self, env):
        def build(root):
            for phase in ("gate", "gate-retry"):
                put(root / "skills", 210, phase, "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", ONE_HIGH)
            write_jsonl(root / "skills" / "dispositions-210.jsonl", [{"id": "codex-gate-1", "outcome": "fixed", "sha": "a"}])
        rows = self.cache_rows(env, build)
        gate = rows["skills/210/codex-gate/1/codex-adversarial-210-gate"]["findings"][0]
        retry = rows["skills/210/codex-gate/1/codex-adversarial-210-gate-retry"]["findings"][0]
        assert gate["outcome"] == "fixed"
        assert retry["outcome"] == "unknown"
        assert "already credits" in retry["outcome_status"]["reason"]

    def test_the_same_record_under_the_alias_directories_gives_two_rows(self, env):
        def build(root):
            for d in ("skills", "agent-skills"):
                put(root / d, 211, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)
        rows = [rid for rid in self.cache_rows(env, build) if "/211/codex-gate/" in rid]
        assert len(rows) == 2


class TestCodexReport:
    def report(self, env, *extra):
        cache = env.tmp / "cache"
        build_codex_cache(cache)
        env.harvest(cache)
        out = env.run("report", "--ledger", env.ledger, "--format", "json", *extra)
        assert out.returncode == 0, out.stderr
        return {t["type"]: t for t in json.loads(out.stdout)["types"]}

    def write_weights(self, env):
        p = env.tmp / "weights.json"
        p.write_text(json.dumps({"high": 6, "medium": 2, "low": 1, "hard": 3, "judgement": 1}))
        return p

    def test_the_three_phases_are_separate_table_rows(self, env):
        types = self.report(env)
        for phase in ("codex-gate", "codex-second", "codex-third"):
            assert phase in types

    def test_codex_value_uses_the_codex_weights(self, env):
        # ticket 200 gate: high fixed = 3, medium leftover = 0. 206 gate: high fixed shared with spec = 3/2,
        # medium unknown = 0. Gate rows also hold 204's clean retry and 300's clean pass.
        gate = self.report(env)["codex-gate"]
        assert gate["value"] == 4.5
        assert self.report(env, "--weights", self.write_weights(env))["codex-gate"]["value"] == 9.0

    def test_a_refused_row_is_counted_as_refused_and_never_as_a_clean_pass(self, env):
        gate = self.report(env)["codex-gate"]
        assert gate["refused_rows"] == 1
        # 201 (refused), 202 and 203 have refused or unknown findings: none is a known-empty pass.
        # The clean ones are 204's retry, 205 and 300.
        assert gate["clean_rows"] == 3
        assert self.report(env)["codex-third"]["refused_rows"] == 0

    def test_a_refused_row_is_not_an_unknown_findings_row_and_a_claude_type_has_no_clean_column(self, env):
        types = self.report(env)
        # 202 (unparsed) and 203 (no .out) only: the refused 201 is counted in `refused_rows`, once.
        assert types["codex-gate"]["unknown_finding_rows"] == 2
        assert types["spec"]["clean_rows"] is None

    def test_codex_cost_is_wall_clock_with_no_tokens_or_dollars(self, env):
        gate = self.report(env)["codex-gate"]
        assert gate["tokens"] is None
        assert gate["dollars"] is None
        assert gate["unknown_cost_rows"] == 1  # 205's unparseable timestamps
        assert gate["wall_clock_seconds"] > 0
