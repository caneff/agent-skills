"""Tests for review_ledger.py (#1265). Every test runs a subcommand's command
line on a fixture tree and reads what comes out: ledger rows, the review file,
or the report. Nothing here calls the module's functions, and every run points
HOME at a temp dir so no default path can reach the real ~/.cache."""
import json

import pytest

from review_ledger_support import (PRICES, build_cache, build_cost_fixture, cost_rows, finding, report_rows,
                                   section, write_jsonl)


class TestHarvest:
    @pytest.fixture
    def env(self, env):
        env.cache = env.tmp / "cache"
        build_cache(env.cache)
        env.harvest(env.cache)
        return env

    def outcomes(self, env, row_id):
        return {f["id"]: (f["outcome"], f["severity"]) for f in env.rows()[row_id]["findings"]}

    def test_one_row_per_axis_run_plus_oe_split(self, env):
        assert sorted(env.rows()) == [
            "skills/100/correctness/1/findings-correctness-100",
            "skills/100/over-engineering/1/findings-standards-100",
            "skills/100/spec/1/findings-spec-100",
            "skills/100/standards/1/findings-standards-100",
            "skills/101/standards/1/findings-standards-101",
            "skills/102/verification/1/findings-verify-102",
            "skills/103/spec/1/findings-spec-103",
            "skills/104/over-engineering/1/findings-standards-104",
            "skills/104/standards/1/findings-standards-104",
            "skills/105/spec/1/findings-spec-105",
            "skills/105/standards/1/findings-standards-105",
            "skills/106/over-engineering/2/findings-standards-106-r2",
            "skills/106/standards/2/findings-standards-106-r2",
            "skills/107/spec/1/findings-spec-107-108",
            "skills/110/correctness/1/findings-correctness-110",
            "skills/111/spec/1/findings-spec-111",
            "skills/112/spec/2/findings-spec-112",
        ]

    def test_oe_finding_leaves_the_standards_row(self, env):
        assert self.outcomes(env, "skills/100/standards/1/findings-standards-100") == \
            {"S1": ("fixed", "hard"), "S2": ("fixed", "judgement")}
        assert self.outcomes(env, "skills/100/over-engineering/1/findings-standards-100") == \
            {"OE1": ("leftover", "judgement")}

    def test_severity_joined_from_findings_not_from_dispositions(self, env):
        # OE1's disposition says "judgement, PLAUSIBLE"; the findings sidecar says judgement.
        assert self.outcomes(env, "skills/100/spec/1/findings-spec-100")["P1"] == ("fixed", "hard")
        assert self.outcomes(env, "skills/100/over-engineering/1/findings-standards-100")["OE1"][1] == \
            "judgement"

    def test_drifted_labels_map_to_canonical(self, env):
        assert self.outcomes(env, "skills/100/spec/1/findings-spec-100")["P2"][0] == "disputed"
        assert self.outcomes(env, "skills/100/correctness/1/findings-correctness-100")["C2"][0] == "leftover"
        assert self.outcomes(env, "skills/103/spec/1/findings-spec-103")["P1"][0] == "fixed"
        assert finding_of(env, "skills/100/standards/1/findings-standards-100", "S2")["partial"]
        assert not finding_of(env, "skills/100/spec/1/findings-spec-100", "P1")["partial"]

    def test_a_row_lists_each_label_mapping_it_applied_as_from_and_to(self, env):
        assert env.rows()["skills/100/standards/1/findings-standards-100"]["status"]["mappings"] == \
            [{"from": "partial", "to": "fixed+partial"}]

    def test_an_unknown_outcome_is_never_a_partial_fix(self, env):
        rows = env.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
        unknown = [f for f in rows if f["outcome"] == "unknown"]
        assert unknown
        for f in unknown:
            assert not f["partial"], f["id"]

    def test_not_fixed_is_read_from_its_own_words(self, env):
        rows = env.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
        by_id = {f["id"]: f["outcome"] for f in rows}
        assert by_id["C3"] == "leftover"  # a reason saying the fix did not land is not a dispute
        assert by_id["C2"] == "leftover"

    @pytest.mark.parametrize("fid", ["C1", "C4", "C5", "C6", "C7", "C8"])
    def test_every_unmapped_or_malformed_outcome_is_unknown(self, env, fid):
        rows = env.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
        by_id = {f["id"]: f["outcome"] for f in rows}
        assert by_id[fid] == "unknown", fid

    def test_round_comes_from_the_id_prefix_and_oe_keeps_its_round(self, env):
        rows = env.rows()
        assert rows["skills/106/standards/2/findings-standards-106-r2"]["round"] == 2
        oe = rows["skills/106/over-engineering/2/findings-standards-106-r2"]
        assert [f["id"] for f in oe["findings"]] == ["r2-OE1"]

    def test_multi_ticket_clump_rows_carry_every_ticket_and_join_their_dispositions(self, env):
        row = env.rows()["skills/107/spec/1/findings-spec-107-108"]
        assert row["tickets"] == [107, 108]
        assert row["findings"][0]["outcome"] == "fixed"

    def test_off_pattern_sidecars_are_listed_not_dropped(self, env):
        text = section(env.review.read_text(), "Sidecars not harvested")
        assert "findings-spec2-109.jsonl" in text
        assert "dispositions-109-v2.jsonl" in text
        assert not any("/109/" in rid for rid in env.rows())

    def test_empty_or_truncated_sidecar_is_unknown_findings_not_a_clean_review(self, env):
        empty = env.rows()["skills/110/correctness/1/findings-correctness-110"]
        assert empty["status"]["fields"]["findings"]["status"] == "unknown"
        half = env.rows()["skills/111/spec/1/findings-spec-111"]
        assert half["status"]["fields"]["findings"]["status"] == "unknown"
        assert [f["id"] for f in half["findings"]] == ["P1"]
        assert "findings-spec-111.jsonl: 1 unreadable line" in env.review.read_text().split("## Skipped lines")[1]
        clean = env.rows()["skills/100/spec/1/findings-spec-100"]
        assert clean["status"]["fields"]["findings"]["status"] == "known"

    def test_verify_axis_becomes_verification(self, env):
        row = env.rows()["skills/102/verification/1/findings-verify-102"]
        assert row["type"] == "verification"
        # not-fixed with neither a reason nor a text is not readable as leftover or disputed.
        assert row["findings"][0]["outcome"] == "unknown"
        # The file-name mapping is the row's own, not only the review file's (P4, #1406).
        assert {"from": "verify", "to": "verification (axis in filename)"} in row["status"]["mappings"]

    def test_alias_repo_folds_onto_skills(self, env):
        assert env.rows()["skills/103/spec/1/findings-spec-103"]["repo"] == "skills"

    def test_unmapped_outcome_is_unknown_in_row_and_listed(self, env):
        c1 = finding_of(env, "skills/100/correctness/1/findings-correctness-100", "C1")
        assert c1["outcome"] == "unknown"
        assert c1["outcome_status"]["status"] == "unknown"
        assert "fixed-with-regression" in c1["outcome_status"]["reason"]
        assert "fixed-with-regression" in section(env.review.read_text(), "Unmapped values")

    @pytest.mark.parametrize("label", ["partial", "fixed-partial", "not-fixed", "not_fixed", "verify"])
    def test_every_applied_mapping_is_listed(self, env, label):
        assert f"`{label}`" in section(env.review.read_text(), "Label mappings applied")

    def test_missing_dispositions_file_is_unknown_not_leftover(self, env):
        row = env.rows()["skills/101/standards/1/findings-standards-101"]
        assert row["findings"][0]["outcome"] == "unknown"
        assert "no dispositions file" in row["findings"][0]["outcome_status"]["reason"]

    def test_shared_finding_marked_on_both_reviewers(self, env):
        s1 = finding_of(env, "skills/100/standards/1/findings-standards-100", "S1")
        p1 = finding_of(env, "skills/100/spec/1/findings-spec-100", "P1")
        assert (s1["overlap"], s1["k"]) == ("shared", 2)
        assert (p1["overlap"], p1["k"]) == ("shared", 2)
        p2 = finding_of(env, "skills/100/spec/1/findings-spec-100", "P2")
        assert (p2["overlap"], p2["k"]) == ("unique", 1)

    @pytest.mark.parametrize("row_id", ["skills/104/standards/1/findings-standards-104",
                                        "skills/104/over-engineering/1/findings-standards-104"])
    def test_oe_and_standards_are_one_reviewer(self, env, row_id):
        # OE1 and S2 share no file, but an OE match with its own standards report would not be overlap.
        f = env.rows()[row_id]["findings"][0]
        assert (f["overlap"], f["k"]) == ("unique", 1), row_id

    def test_a_reviewer_matching_its_own_oe_cut_is_not_an_overlap_match(self, env):
        assert "Dead branch" not in section(env.review.read_text(), "Overlap matches")

    @pytest.mark.parametrize("row_id", ["skills/105/standards/1/findings-standards-105",
                                        "skills/105/spec/1/findings-spec-105"])
    def test_same_title_in_different_files_is_not_a_match(self, env, row_id):
        f = env.rows()[row_id]["findings"][0]
        assert (f["overlap"], f["k"]) == ("unique", 1), row_id

    def test_every_match_is_written_with_both_titles(self, env):
        text = section(env.review.read_text(), "Overlap matches")
        assert "Duplicated helper loader" in text
        assert "duplicated loader helper" in text
        assert "Long function" not in text
        assert "Jaccard" in text

    def test_a_match_line_names_each_side_by_type_then_id(self, env):
        assert '\n- skills #100 `./a.py`: spec P1 "duplicated loader helper"' \
               ' = standards S1 "Duplicated helper loader"\n' in section(env.review.read_text(), "Overlap matches")

    def test_without_transcripts_cost_is_unknown_never_zero_and_oe_is_inside_standards(self, env):
        for row in env.rows().values():
            for field in ("tokens", "wall_clock"):
                want = "inside-standards" if row["type"] == "over-engineering" else "unknown"
                assert row["cost"][field]["status"] == want
                assert "value" not in row["cost"][field]
            assert row["cost"]["usage_delta"]["status"] == "not-applicable"

    def test_dispositions_with_no_finding_are_listed_not_dropped(self, env):
        assert "codex-gate-1" in section(env.review.read_text(), "Dispositions with no finding")


class TestMappingLabel:
    """A drifted label is data: one holding the review file's own ` -> ` separator
    (#1276) is listed whole, not split at the wrong arrow."""

    def test_label_containing_an_arrow_is_listed_whole(self, env):
        cache = env.tmp / "cache"
        write_jsonl(cache / "skills" / "findings-standards-300.jsonl",
                    [finding("S1", "hard", "a.py", "Some finding")])
        write_jsonl(cache / "skills" / "dispositions-300.jsonl",
                    [{"id": "S1", "outcome": "fixed -> shipped", "sha": "abc1234"}])
        env.harvest(cache)
        assert "- `fixed -> shipped` -> unknown: 1" in section(env.review.read_text(), "Unmapped values")


class TestVerificationOverlap:
    """Ruling 8 (P6 on PR #1275): the verification pass never counts toward
    overlap for a round-1 finding it re-checks."""

    @pytest.fixture
    def env(self, env):
        skills = env.tmp / "cache" / "skills"
        write_jsonl(skills / "findings-standards-200.jsonl", [finding("S1", "hard", "a.py", "Widget leak on close")])
        write_jsonl(skills / "findings-verify-200.jsonl", [
            finding("V1", "judgement", "a.py", "widget leak on close", axis="verify"),
            finding("V2", "judgement", "b.py", "Fix left a stale docstring", axis="verify")])
        write_jsonl(skills / "dispositions-200.jsonl", [
            {"id": "S1", "outcome": "fixed", "sha": "e"}, {"id": "V1", "outcome": "fixed", "sha": "e"},
            {"id": "V2", "outcome": "fixed", "sha": "e"}])
        env.harvest(env.tmp / "cache")
        return env

    def find(self, env, kind, fid):
        row = next(r for r in env.rows().values() if r["type"] == kind)
        return next(f for f in row["findings"] if f["id"] == fid)

    def test_restated_round_one_finding_stays_unique(self, env):
        f = self.find(env, "standards", "S1")
        assert (f["overlap"], f["k"]) == ("unique", 1)

    def test_the_restating_verification_finding_earns_no_credit(self, env):
        f = self.find(env, "verification", "V1")
        assert (f["overlap"], f["k"]) == ("restated", 1)
        out = json.loads(env.run("report", "--ledger", env.ledger, "--format", "json").stdout)
        verification = next(t for t in out["types"] if t["type"] == "verification")
        # V1 restates S1 (fixed, judgement 1, would be worth 1); only V2 counts.
        assert verification["value"] == 1.0
        standards = next(t for t in out["types"] if t["type"] == "standards")
        assert standards["value"] == 3.0  # S1 hard, unique, undivided

    def test_finding_the_verification_pass_raises_new_keeps_its_credit(self, env):
        f = self.find(env, "verification", "V2")
        assert (f["overlap"], f["k"]) == ("unique", 1)

    def test_restatement_is_listed_apart_from_overlap_matches(self, env):
        text = env.review.read_text()
        assert "Widget leak" not in section(text, "Overlap matches")
        assert "Widget leak" in section(text, "Verification restatements")


class TestCostHarvest:
    @pytest.fixture
    def env(self, env):
        env.cache, env.tr = build_cost_fixture(env.tmp)
        r = env.run("harvest", "--cache", env.cache, "--transcripts", env.tr, "--ledger", env.ledger,
                    "--review-file", env.review)
        assert r.returncode == 0, r.stderr
        return env

    def cost(self, env, row_id):
        return env.rows()[row_id]["cost"]

    def tokens_of(self, env, row_id):
        return self.cost(env, row_id)["tokens"]

    def unattributed_section(self, env):
        return section(env.review.read_text(), "Transcripts not attributed")

    def test_tokens_by_kind_from_the_axis_transcript_deduping_streamed_lines(self, env):
        t = self.cost(env, "skills/400/standards/1/findings-standards-400")["tokens"]
        assert t == {"status": "known", "input": 5, "output": 120, "cache_write": 120, "cache_read": 210}

    def test_two_reviewers_of_one_pr_each_get_their_own_transcript(self, env):
        spec = self.cost(env, "skills/400/spec/1/findings-spec-400")["tokens"]
        corr = self.cost(env, "skills/400/correctness/1/findings-correctness-400")["tokens"]
        assert (spec["input"], spec["output"], spec["cache_write"], spec["cache_read"]) == (10, 20, 30, 40)
        assert (corr["input"], corr["output"], corr["cache_write"], corr["cache_read"]) == (1, 2, 3, 4)

    def test_the_same_ticket_number_in_another_repo_is_not_mixed_in(self, env):
        other = self.cost(env, "otherrepo/400/standards/1/findings-standards-400")["tokens"]
        assert other["input"] == 7
        assert self.cost(env, "skills/400/standards/1/findings-standards-400")["tokens"]["input"] == 5

    def test_wall_clock_is_first_to_last_timestamp(self, env):
        w = self.cost(env, "skills/400/standards/1/findings-standards-400")["wall_clock"]
        assert (w["status"], w["seconds"]) == ("known", 330)
        assert (w["start"], w["end"]) == ("2026-09-20T10:00:00.000Z", "2026-09-20T10:05:30.000Z")

    def test_row_model_is_read_from_the_transcript(self, env):
        assert env.rows()["skills/400/spec/1/findings-spec-400"]["model"] == "claude-opus-5-5"

    def test_round_two_transcript_attributes_to_the_round_two_row(self, env):
        assert self.cost(env, "skills/404/standards/2/findings-standards-404-r2")["tokens"]["input"] == 6

    def test_verification_transcript_attributes_to_the_verify_sidecar_row(self, env):
        assert self.cost(env, "skills/403/verification/1/findings-verify-403")["tokens"]["input"] == 5

    def test_transcript_without_usage_is_unknown_tokens_never_zero(self, env):
        c = self.cost(env, "skills/402/standards/1/findings-standards-402")
        assert c["tokens"]["status"] == "unknown"
        assert "usage" in c["tokens"]["reason"]
        for kind in ("input", "output", "cache_write", "cache_read"):
            assert kind not in c["tokens"]
        assert c["wall_clock"]["seconds"] == 120

    @pytest.mark.parametrize("field", ["tokens", "wall_clock"])
    def test_axis_run_with_no_transcript_is_unknown_never_zero(self, env, field):
        c = self.cost(env, "skills/401/standards/1/findings-standards-401")
        assert c[field]["status"] == "unknown", field
        assert "no transcript" in c[field]["reason"]
        assert "input" not in c[field]
        assert "seconds" not in c[field]

    def test_two_transcripts_for_one_row_are_summed_and_both_listed(self, env):
        row = env.rows()["skills/405/spec/1/findings-spec-405"]
        assert row["cost"]["tokens"]["input"] == 3
        assert len([s for s in row["status"]["sources"] if "agent-" in s]) == 2

    def test_over_engineering_cost_stays_inside_standards(self, env):
        oe = self.cost(env, "skills/400/over-engineering/1/findings-standards-400")
        assert oe["tokens"]["status"] == "inside-standards"
        assert oe["wall_clock"]["status"] == "inside-standards"
        assert "input" not in oe["tokens"]

    def test_verification_run_without_a_sidecar_gets_its_own_row(self, env):
        row = next(r for rid, r in env.rows().items() if r["type"] == "verification" and r["ticket"] == 406)
        assert row["cost"]["tokens"]["input"] == 9
        assert row["findings"] == []
        assert row["status"]["fields"]["findings"]["status"] == "unknown"

    def test_unattributable_transcripts_are_listed_with_a_reason_not_dropped(self, env):
        text = self.unattributed_section(env)
        assert "agent-lost" in text
        assert "no ticket" in text
        assert "agent-bad" in text
        assert "agent-gp" not in text  # a non diff-reviewer is out of scope, not a failure

    @pytest.mark.parametrize("unattributed", [99, 500, 77, 66])
    def test_unattributed_spend_is_in_no_row(self, env, unattributed):
        seen = [r["cost"]["tokens"].get("input") for r in env.rows().values()]
        assert unattributed not in seen

    def test_round_is_read_from_the_id_prefix_the_brief_names(self, env):
        assert self.tokens_of(env, "skills/407/standards/2/findings-standards-407-r2")["input"] == 4

    def test_a_message_with_a_malformed_usage_block_makes_tokens_unknown(self, env):
        t = self.tokens_of(env, "skills/408/standards/1/findings-standards-408")
        assert t["status"] == "unknown"
        assert "usage" in t["reason"]

    def test_a_torn_transcript_makes_tokens_unknown(self, env):
        t = self.tokens_of(env, "skills/409/standards/1/findings-standards-409")
        assert t["status"] == "unknown"
        assert "unreadable" in t["reason"]

    def test_a_torn_transcript_or_an_unparseable_timestamp_makes_wall_clock_unknown(self, env):
        torn = self.cost(env, "skills/409/standards/1/findings-standards-409")["wall_clock"]
        assert torn["status"] == "unknown"
        assert "unreadable" in torn["reason"]
        bad = self.cost(env, "skills/418/standards/1/findings-standards-418")["wall_clock"]
        assert bad["status"] == "unknown"
        assert "timestamp" in bad["reason"]

    def test_naive_and_aware_timestamps_do_not_crash_the_harvest(self, env):
        assert self.cost(env, "skills/410/standards/1/findings-standards-410")["wall_clock"]["seconds"] == 60

    def test_a_review_of_a_review_worktree_is_not_charged_to_the_ticket_worktree_it_ran_in(self, env):
        row = self.cost(env, "skills/411/spec/1/findings-spec-411")
        assert row["tokens"]["status"] == "unknown"
        assert "agent-lvl" in self.unattributed_section(env)
        assert "spec-level" in self.unattributed_section(env)

    @pytest.mark.parametrize("rid", ["skills/412/correctness/1/findings-correctness-412",
                                     "skills/412/correctness/1/findings-correctness-412-round1"])
    def test_two_sidecar_rows_for_one_key_both_say_so_rather_than_one_taking_the_cost(self, env, rid):
        t = self.tokens_of(env, rid)
        assert t["status"] == "unknown", rid
        assert "share" in t["reason"]

    def test_two_sidecar_rows_for_one_key_leave_no_transcript_only_row(self, env):
        assert not [r for r in env.rows() if r.startswith("skills/412/") and r.endswith("/agent-twin")]

    def test_a_repo_spelled_with_an_underscore_matches_its_project_directory(self, env):
        assert self.tokens_of(env, "foo_bar/413/standards/1/findings-standards-413")["input"] == 4
        assert not [r for r in env.rows() if r.startswith("foo-bar/")]

    def test_a_worktree_not_named_implement_n_is_listed_because_its_repo_cannot_be_told(self, env):
        # .../src/drills/.claude/worktrees/<name> may be a checkout of a different repo than "drills".
        assert self.tokens_of(env, "otherrepo/414/standards/1/findings-standards-414")["status"] == "unknown"
        assert "agent-drl" in self.unattributed_section(env)
        assert "not implement-N" in self.unattributed_section(env)
        assert not [r for r in env.rows() if r.startswith("otherrepo--") or "drills" in r]

    def test_a_verification_run_joins_the_only_verify_row_when_its_round_differs(self, env):
        assert self.tokens_of(env, "skills/415/verification/1/findings-verify-415")["input"] == 4

    def test_description_and_first_message_naming_different_axes_is_listed_not_guessed(self, env):
        assert self.tokens_of(env, "skills/416/standards/1/findings-standards-416")["status"] == "unknown"
        assert "agent-cfl" in self.unattributed_section(env)

    def test_transcripts_behind_a_shared_key_are_listed(self, env):
        text = section(env.review.read_text(), "Transcripts behind a key several sidecar rows share")
        assert "agent-twin" in text

    def test_an_unreadable_transcript_is_listed_and_does_not_stop_the_harvest(self, env):
        assert "agent-dir" in self.unattributed_section(env)

    def test_rows_that_sum_several_transcripts_are_listed(self, env):
        assert "findings-spec-405" in section(env.review.read_text(), "Rows with more than one transcript")

    def test_reharvest_gives_the_same_ledger(self, env):
        first = env.ledger.read_text()
        r = env.run("harvest", "--cache", env.cache, "--transcripts", env.tr, "--ledger", env.ledger,
                    "--review-file", env.review)
        assert r.returncode == 0, r.stderr
        assert env.ledger.read_text() == first

    def test_missing_explicit_transcripts_tree_fails_loud(self, env):
        r = env.run("harvest", "--cache", env.cache, "--transcripts", env.tmp / "nope", "--ledger",
                    env.tmp / "l2.jsonl", "--review-file", env.tmp / "r2.md")
        assert r.returncode == 2

    def test_default_transcripts_tree_missing_is_unknown_cost_not_a_failure(self, env):
        r = env.run("harvest", "--cache", env.cache, "--ledger", env.tmp / "l3.jsonl",
                    "--review-file", env.tmp / "r3.md")
        assert r.returncode == 0, r.stderr
        rows = [json.loads(x) for x in (env.tmp / "l3.jsonl").read_text().splitlines()]
        assert all(r["cost"]["tokens"]["status"] in ("unknown", "inside-standards") for r in rows)
        unknown = [r for r in rows if r["cost"]["tokens"]["status"] == "unknown"]
        assert unknown
        for row in unknown:
            assert "transcripts tree not found" in row["cost"]["tokens"]["reason"], row["row_id"]


class TestHarvestRerun:
    def test_same_tree_twice_gives_identical_ledger(self, env):
        cache = env.tmp / "cache"
        build_cache(cache)
        env.harvest(cache)
        first = env.ledger.read_text()
        env.harvest(cache)
        assert env.ledger.read_text() == first
        assert len(first.splitlines()) == 17

    def test_a_row_no_longer_in_the_cache_leaves_the_ledger(self, env):
        cache = env.tmp / "cache"
        build_cache(cache)
        env.harvest(cache)
        (cache / "skills" / "findings-standards-101.jsonl").rename(cache / "skills" / "notes-101.txt")
        env.harvest(cache)
        assert len(env.ledger.read_text().splitlines()) == 16
        assert "skills/101/standards/1/findings-standards-101" not in env.ledger.read_text()

    def test_rows_not_written_by_harvest_survive_a_reharvest(self, env):
        cache = env.tmp / "cache"
        build_cache(cache)
        env.harvest(cache)
        other = {"row_id": "skills/9/codex-gate/1/x", "origin": "append", "type": "codex-gate", "findings": []}
        with env.ledger.open("a") as fh:
            fh.write(json.dumps(other) + "\n")
        env.harvest(cache)
        assert "skills/9/codex-gate/1/x" in env.ledger.read_text()

    def test_cache_with_no_sidecars_fails_loud(self, env):
        cache = env.tmp / "cache"
        (cache / "skills").mkdir(parents=True)
        result = env.run("harvest", "--cache", cache, "--ledger", env.tmp / "l.jsonl",
                         "--review-file", env.tmp / "r.md")
        assert result.returncode == 2
        assert "no findings or dispositions sidecars" in result.stderr

    def test_corrupt_existing_ledger_fails_loud_and_is_left_alone(self, env):
        cache = env.tmp / "cache"
        build_cache(cache)
        ledger = env.tmp / "l.jsonl"
        ledger.write_text("{not json\n")
        result = env.run("harvest", "--cache", cache, "--ledger", ledger, "--review-file", env.tmp / "r.md")
        assert result.returncode == 2
        assert ledger.read_text() == "{not json\n"

    def test_default_cache_is_under_home_never_the_real_one(self, env):
        result = env.run("harvest", "--ledger", env.tmp / "l.jsonl", "--review-file", env.tmp / "r.md")
        assert result.returncode != 0
        assert str(env.home) in result.stderr


class TestCostReport:
    def report(self, env, prices=PRICES, *extra, fmt="json"):
        ledger = env.tmp / "in.jsonl"
        write_jsonl(ledger, cost_rows())
        args = ["report", "--ledger", ledger, "--format", fmt, *extra]
        if prices is not None:
            pf = env.tmp / "prices.json"
            pf.write_text(json.dumps(prices))
            args += ["--prices", pf]
        result = env.run(*args)
        assert result.returncode == 0, result.stderr
        if fmt != "json":
            return result.stdout
        out = json.loads(result.stdout)
        self.notes = out["notes"]
        return {t["type"]: t for t in out["types"]}

    def test_dollars_match_the_hand_computed_fixture(self, env):
        # A: 15 + 7.5 + 3.75 + 4.5 = 30.75.  B: 2 x 15 = 30.  D has no price, C no tokens.
        std = self.report(env)["standards"]
        assert std["dollars"] == 60.75
        assert std["tokens"] == {"input": 3_000_010, "output": 100_000, "cache_write": 200_000,
                                 "cache_read": 3_000_000}
        assert std["wall_clock_seconds"] == 155
        # F: 3 + 15 = 18.
        assert self.report(env)["spec"]["dollars"] == 21.0  # plus H: 3

    def test_changing_a_price_changes_the_dollars(self, env):
        dearer = {**PRICES, "m-opus": {**PRICES["m-opus"], "input": 30}}
        # A: 30 + 7.5 + 3.75 + 4.5 = 45.75.  B: 60.
        assert self.report(env, dearer)["standards"]["dollars"] == 105.75

    def test_value_per_dollar_uses_only_rows_with_known_cost_and_findings(self, env):
        # A (3) + its over-engineering E (1) + B (1) over 60.75. C (unknown cost) and D (unpriced) are left out,
        # and so are their over-engineering rows E3 and E4: the OE cost is inside the standards dollars, so
        # its value belongs in the same numerator, and only when the standards row itself is counted.
        assert self.report(env)["standards"]["value_per_dollar"] == round(5 / 60.75, 4)
        # F: 3 / k=2 = 1.5 over 18 dollars; G has no cost, and H has cost but unknown findings.
        assert self.report(env)["spec"]["value_per_dollar"] == round(1.5 / 18, 4)

    def test_unknown_and_unpriced_rows_are_counted_never_averaged_as_zero(self, env):
        std = self.report(env)["standards"]
        assert (std["unknown_cost_rows"], std["unpriced_rows"]) == (1, 1)
        spec = self.report(env)["spec"]
        assert spec["unknown_cost_rows"] == 1

    def test_rows_on_an_unpriced_model_are_named_in_a_note(self, env):
        self.report(env)
        assert any(n.startswith("standards: 1 row(s)") for n in self.notes), self.notes

    def test_no_price_table_means_no_dollars_not_zero_dollars(self, env):
        std = self.report(env, None)["standards"]
        assert std["dollars"] is None
        assert std["value_per_dollar"] is None
        assert "n/a" in self.report(env, None, fmt="md")

    def test_over_engineering_cost_is_inside_standards(self, env):
        oe = self.report(env)["over-engineering"]
        assert oe["cost_note"] == "inside standards"
        assert oe["dollars"] is None
        assert oe["value_per_dollar"] is None
        assert oe["unknown_cost_rows"] == 0
        assert oe["value"] == 1.0 + 3.0 + 3.0  # E + E3 + E4: reported apart in the value column
        line = next(x for x in self.report(env, fmt="md").splitlines() if x.startswith("| over-engineering"))
        assert "inside standards" in line

    def test_markdown_table_carries_the_cost_columns(self, env):
        head = self.report(env, fmt="md").splitlines()[0]
        for col in ("tokens", "wall clock", "dollars", "value per dollar"):
            assert col in head
        line = next(x for x in self.report(env, fmt="md").splitlines() if x.startswith("| spec"))
        assert "$21.00" in line


COUNT_COLUMNS = ("type", "rows", "findings", "value", "unique_share", "leftover_rate", "dispute_rate",
                 "unknown_outcomes", "unweighted", "unknown_finding_rows", "unknown_cost_rows")


class TestReport:
    def report(self, env, *extra, rows=None):
        ledger = env.tmp / "in.jsonl"
        write_jsonl(ledger, rows or report_rows())
        result = env.run("report", "--ledger", ledger, "--format", "json", *extra)
        assert result.returncode == 0, result.stderr
        return {t["type"]: t for t in json.loads(result.stdout)["types"]}

    def count_columns(self, t):
        return {k: t[k] for k in COUNT_COLUMNS}

    def test_table_matches_hand_computed_values(self, env):
        types = self.report(env)
        assert self.count_columns(types["standards"]) == {
            "type": "standards", "rows": 1, "findings": 5, "value": 3.5,
            "unique_share": 0.8, "leftover_rate": 0.25, "dispute_rate": 0.25,
            "unknown_outcomes": 1, "unweighted": 0, "unknown_finding_rows": 1,
            "unknown_cost_rows": 1}
        assert self.count_columns(types["spec"]) == {
            "type": "spec", "rows": 1, "findings": 2, "value": 1.5,
            "unique_share": 0.5, "leftover_rate": 0.0, "dispute_rate": 0.0,
            "unknown_outcomes": 0, "unweighted": 1, "unknown_finding_rows": 0,
            "unknown_cost_rows": 1}

    def test_severity_weights_are_a_parameter(self, env):
        weights = env.tmp / "w.json"
        weights.write_text(json.dumps({"hard": 10, "judgement": 2}))
        types = self.report(env, "--weights", weights)
        # a hard fixed 10 + b judgement filed shared 2/2
        assert types["standards"]["value"] == 11.0
        assert types["spec"]["value"] == 5.0

    def test_overlap_split_divides_a_shared_finding_by_k(self, env):
        types = self.report(env)
        assert types["spec"]["value"] == 1.5  # hard 3 / k=2
        types = self.report(env, "--split", "none")
        assert types["spec"]["value"] == 3.0

    def test_leftover_carries_no_value(self, env):
        only_leftover = [dict(report_rows()[0], findings=[
            {"id": "c", "severity": "hard", "outcome": "leftover", "partial": False,
             "overlap": "unique", "k": 1}])]
        types = self.report(env, rows=only_leftover)
        assert types["standards"]["value"] == 0.0
        assert types["standards"]["leftover_rate"] == 1.0

    def test_a_moved_finding_carries_value_like_a_filed_one(self, env):
        # #1401: `moved` is a valid finding that went onto an open ticket, the
        # successor of `filed` for a finding that needs its own design.
        moved = [dict(report_rows()[0], findings=[
            {"id": "m", "severity": "hard", "outcome": "moved", "partial": False,
             "overlap": "unique", "k": 1}])]
        types = self.report(env, rows=moved)
        assert types["standards"]["value"] == 3.0

    def test_disputed_carries_no_value(self, env):
        only_disputed = [dict(report_rows()[0], findings=[
            {"id": "d", "severity": "hard", "outcome": "disputed", "partial": False,
             "overlap": "unique", "k": 1}])]
        types = self.report(env, rows=only_disputed)
        assert types["standards"]["value"] == 0.0
        assert types["standards"]["dispute_rate"] == 1.0

    def test_markdown_table_and_mutation_note(self, env):
        ledger = env.tmp / "in.jsonl"
        write_jsonl(ledger, report_rows())
        result = env.run("report", "--ledger", ledger)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        # Only the leading cells: a column added or reordered after them is not this test's business.
        assert any(l.startswith("| standards | 1 | 5 | 3.50 | 80.0% | 25.0% | 25.0% | 1 | 0 | 1 | 1 |")
                   for l in lines), lines
        assert "Reviews before #1270 carry no mutation data" in result.stdout
        assert "No mutation rows" in result.stdout

    def test_a_type_outside_the_known_list_is_still_reported(self, env):
        odd = dict(report_rows()[0], row_id="r9", type="future-review")
        assert "future-review" in self.report(env, rows=[odd])

    def test_mutation_note_only_when_no_mutation_rows(self, env):
        ledger = env.tmp / "in.jsonl"
        mut = dict(report_rows()[0], row_id="r8", type="worker-mutation")
        write_jsonl(ledger, [mut])
        result = env.run("report", "--ledger", ledger)
        assert "No mutation rows" not in result.stdout

    def test_a_prices_file_that_is_not_an_object_fails_loud(self, env):
        ledger, prices = env.tmp / "in.jsonl", env.tmp / "p.json"
        write_jsonl(ledger, report_rows())
        prices.write_text("[1, 2]")
        result = env.run("report", "--ledger", ledger, "--prices", prices)
        assert result.returncode == 2

    def test_missing_ledger_fails_loud(self, env):
        result = env.run("report", "--ledger", env.tmp / "absent.jsonl")
        assert result.returncode != 0
