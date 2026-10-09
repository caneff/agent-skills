"""Tests for `review_ledger.py append` (#1268). Every test runs the command line on
the fixture trees `review_ledger_support.py` builds and reads the ledger it leaves;
HOME is a temp dir, so no default path reaches the real ~/.cache or ~/.claude."""
import fcntl
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from review_ledger_support import (SCRIPT, SKILLS_PROJ, build_cost_fixture, finding, transcript, usage,
                                   write_jsonl, wt)


class Appender:
    """The cost fixture's cache and transcripts, and the `append`/`harvest` commands over them."""

    def __init__(self, env):
        self.env = env
        self.tmp = env.tmp
        self.home = env.home
        self.cache, self.tr = build_cost_fixture(env.tmp)
        self.ledger = env.ledger
        self.rows = env.rows
        self.run = env.run

    def append(self, ticket, rtype, rnd=1, repo="skills", cache=None, tr=None):
        return self.run("append", "--repo", repo, "--ticket", ticket, "--type", rtype, "--round", rnd,
                        "--cache", cache or self.cache, "--transcripts", tr or self.tr, "--ledger", self.ledger)

    def ok(self, *a, **k):
        r = self.append(*a, **k)
        assert r.returncode == 0, r.stderr
        return r

    def harvest(self, tr=None):
        r = self.run("harvest", "--cache", self.cache, "--transcripts", tr or self.tr, "--ledger", self.ledger,
                     "--review-file", self.tmp / "h.md")
        assert r.returncode == 0, r.stderr
        return r

    def harvested(self):
        other = self.tmp / "harvested.jsonl"
        r = self.run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", other,
                     "--review-file", self.tmp / "h.md")
        assert r.returncode == 0, r.stderr
        return {r["row_id"]: r for r in map(json.loads, other.read_text().splitlines())}


@pytest.fixture
def ap(env):
    return Appender(env)


class TestAppendRow:
    def test_a_later_append_keeps_a_claude_and_codex_finding_shared_on_both_sides(self, ap):
        skills = ap.cache / "skills"
        (skills / "codex-adversarial-400-gate.json").write_text(json.dumps({
            "ticket": 400, "phase": "gate", "status": 0, "started": "2026-09-22T09:00:00-04:00",
            "completed": "2026-09-22T09:01:00-04:00"}))
        (skills / "codex-adversarial-400-gate.out").write_text(
            "Findings:\n- [high] Thing 400 (a.py:1)\n  Body.\n\nNext steps:\n- Fix.\n")
        ap.harvest()
        ap.ok(400, "standards")
        rows = ap.rows()
        codex = rows["skills/400/codex-gate/1/codex-adversarial-400-gate"]["findings"][0]
        std = next(f for f in rows["skills/400/standards/1/findings-standards-400"]["findings"] if f["id"] == "S1")
        assert (codex["overlap"], codex["k"]) == ("shared", 2)
        assert (std["overlap"], std["k"]) == ("shared", 2)

    def test_writes_the_row_harvest_writes_for_the_same_inputs(self, ap):
        ap.ok(400, "standards")
        ap.ok(400, "spec")
        ap.ok(400, "correctness")
        want = ap.harvested()
        got = ap.rows()
        assert len(got) == 4  # standards, over-engineering, spec, correctness
        for row_id, row in got.items():
            assert row["origin"] == "append"
            assert {**row, "origin": "harvest"} == want[row_id], row_id

    def test_a_standards_append_writes_the_over_engineering_row_with_cost_inside_standards(self, ap):
        ap.ok(400, "standards")
        oe = ap.rows()["skills/400/over-engineering/1/findings-standards-400"]
        assert oe["cost"]["tokens"]["status"] == "inside-standards"
        assert len(ap.rows()) == 2

    def test_the_verification_pass_and_a_later_round_append_too(self, ap):
        ap.ok(403, "verification")
        ap.ok(404, "standards", 2)
        assert sorted(ap.rows()) == [
            "skills/403/verification/1/findings-verify-403",
            "skills/404/standards/2/findings-standards-404-r2"]

    def test_appending_the_same_run_twice_leaves_one_row(self, ap):
        ap.ok(403, "verification")
        first = ap.ledger.read_text()
        ap.ok(403, "verification")
        assert ap.ledger.read_text() == first
        assert len(first.splitlines()) == 1

    def test_a_later_harvest_leaves_exactly_the_rows_a_harvest_alone_writes(self, ap):
        ap.ok(403, "verification")
        ap.harvest()
        assert sorted(ap.rows()) == sorted(ap.harvested())

    def test_a_harvest_after_the_sidecars_are_pruned_keeps_the_rows_and_adds_no_second_cost(self, ap):
        # #1304: the prune takes ticket 400's sidecars; its transcripts outlive them.
        ap.ok(400, "spec")
        appended = ap.rows()
        ap.harvest()
        for name in ("findings-spec-400.jsonl", "findings-standards-400.jsonl", "findings-correctness-400.jsonl",
                     "dispositions-400.jsonl"):
            (ap.cache / "skills" / name).unlink()
        ap.harvest()
        rows = ap.rows()
        assert rows["skills/400/spec/1/findings-spec-400"] == appended["skills/400/spec/1/findings-spec-400"]
        # The spec transcript's cost is held by the appended row: no transcript-only spec row beside it.
        assert [k for k in rows if k.startswith("skills/400/spec/")] == ["skills/400/spec/1/findings-spec-400"]

    def test_a_harvest_keeps_a_later_rounds_row_from_a_sidecar_an_appended_row_shares(self, ap):
        # One sidecar holds round 1 and round 2 ids; only round 1 was appended, so its sources are held.
        write_jsonl(ap.cache / "skills" / "findings-spec-600.jsonl", [
            finding("P1", "hard", "a.py", "First", axis="spec"), finding("r2-P2", "hard", "b.py", "Second", axis="spec")])
        write_jsonl(ap.cache / "skills" / "dispositions-600.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"}])
        transcript(ap.tr, wt(SKILLS_PROJ, 600), "p", "Spec review #600", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(600, "spec")
        ap.harvest()
        assert sorted(k for k in ap.rows() if "/600/" in k) == \
            ["skills/600/spec/1/findings-spec-600", "skills/600/spec/2/findings-spec-600"]

    def test_a_harvest_after_transcript_cleanup_keeps_the_known_cost_and_model(self, ap):
        ap.ok(400, "spec")
        appended = ap.rows()["skills/400/spec/1/findings-spec-400"]
        empty = ap.tmp / "cleaned"
        empty.mkdir()
        ap.harvest(tr=empty)
        row = ap.rows()["skills/400/spec/1/findings-spec-400"]
        assert row["cost"] == appended["cost"]
        assert (row["model"], row["status"]["fields"]["model"]) == \
            (appended["model"], appended["status"]["fields"]["model"])

    def test_a_harvest_after_one_of_two_transcripts_is_cleaned_up_keeps_the_summed_cost(self, ap):
        # Ticket 405's spec review ran twice, in two sessions; cleanup takes the second session first.
        ap.ok(405, "spec")
        appended = ap.rows()["skills/405/spec/1/findings-spec-405"]
        for name in ("agent-sp2.jsonl", "agent-sp2.meta.json"):
            (ap.tr / wt(SKILLS_PROJ, 405) / "s2" / "subagents" / name).unlink()
        ap.harvest()
        assert ap.rows()["skills/405/spec/1/findings-spec-405"]["cost"] == appended["cost"]

    def test_a_harvest_adds_a_retry_transcript_written_after_the_append(self, ap):
        # codex-second-1 (#1406): the append counted one run; a retry of the same review lands later.
        ap.ok(400, "spec")
        transcript(ap.tr, wt(SKILLS_PROJ, 400), "spec2", "Spec review #400 retry", "Repo: x",
                   [("2026-09-20T12:00:00.000Z", "m1", usage(1000, 0, 0, 0))], session="s2")
        ap.harvest()
        row = ap.rows()["skills/400/spec/1/findings-spec-400"]
        assert row["cost"]["tokens"]["input"] == 10 + 1000

    def test_a_harvest_reads_a_transcript_that_grew_after_the_append(self, ap):
        ap.ok(400, "spec")
        transcript(ap.tr, wt(SKILLS_PROJ, 400), "spec", "Spec review #400", "Repo: x", [
            ("2026-09-20T10:00:00.000Z", "m1", usage(10, 20, 30, 40)),
            ("2026-09-20T10:01:00.000Z", "m2", usage(0, 0, 0, 0)),
            ("2026-09-20T10:09:00.000Z", "m3", usage(500, 0, 0, 0))])
        ap.harvest()
        cost = ap.rows()["skills/400/spec/1/findings-spec-400"]["cost"]
        assert (cost["tokens"]["input"], cost["wall_clock"]["seconds"]) == (510, 540)

    def test_a_harvest_after_one_rounds_sidecar_is_pruned_counts_each_transcript_once(self, ap):
        skills = ap.cache / "skills"
        write_jsonl(skills / "findings-verify-700.jsonl", [finding("V1", "judgement", "v.py", "One", axis="verify")])
        write_jsonl(skills / "findings-verify-700-r2.jsonl", [finding("r2-V1", "judgement", "w.py", "Two", axis="verify")])
        transcript(ap.tr, wt(SKILLS_PROJ, 700), "v1", "Verification pass #700", "Verification of round 1",
                   [("2026-09-20T10:00:00Z", "m1", usage(100, 0, 0, 0))])
        transcript(ap.tr, wt(SKILLS_PROJ, 700), "v2", "Verification pass round 2 #700", "Verification of round 2",
                   [("2026-09-21T10:00:00Z", "m1", usage(1, 0, 0, 0))])
        ap.ok(700, "verification", 1)
        ap.ok(700, "verification", 2)
        (skills / "findings-verify-700.jsonl").unlink()  # round 1 is older, so the prune takes it first
        ap.harvest()
        rows = [r for r in ap.rows().values() if r["ticket"] == 700]
        assert sorted(r["cost"]["tokens"]["input"] for r in rows) == [1, 100]

    def test_a_harvest_never_adds_an_appended_rows_transcript_to_a_harvested_row(self, ap):
        # codex-gate-1 / V1: round 1 appended, round 2 only harvested, round 1's sidecar pruned.
        skills = ap.cache / "skills"
        write_jsonl(skills / "findings-verify-700.jsonl", [finding("V1", "judgement", "v.py", "One", axis="verify")])
        write_jsonl(skills / "findings-verify-700-r2.jsonl", [finding("r2-V1", "judgement", "w.py", "Two", axis="verify")])
        transcript(ap.tr, wt(SKILLS_PROJ, 700), "v1", "Verification pass #700", "Verification of round 1",
                   [("2026-09-20T10:00:00Z", "m1", usage(100, 0, 0, 0))])
        transcript(ap.tr, wt(SKILLS_PROJ, 700), "v2", "Verification pass round 2 #700", "Verification of round 2",
                   [("2026-09-21T10:00:00Z", "m1", usage(1, 0, 0, 0))])
        ap.ok(700, "verification", 1)
        (skills / "findings-verify-700.jsonl").unlink()
        ap.harvest()
        rows = [r for r in ap.rows().values() if r["ticket"] == 700]
        assert sorted(r["cost"]["tokens"]["input"] for r in rows) == [1, 100]

    def test_a_harvest_after_the_dispositions_are_pruned_keeps_the_known_outcomes(self, ap):
        ap.ok(400, "spec")
        (ap.cache / "skills" / "dispositions-400.jsonl").unlink()
        ap.harvest()
        (p1,) = ap.rows()["skills/400/spec/1/findings-spec-400"]["findings"]
        assert (p1["outcome"], p1["outcome_status"]) == ("fixed", {"status": "known"})

    def test_a_harvest_after_the_dispositions_are_pruned_keeps_the_label_mappings(self, ap):
        write_jsonl(ap.cache / "skills" / "findings-spec-430.jsonl", [finding("P1", "hard", "a.py", "Half", axis="spec")])
        write_jsonl(ap.cache / "skills" / "dispositions-430.jsonl", [{"id": "P1", "outcome": "partial", "sha": "e"}])
        transcript(ap.tr, wt(SKILLS_PROJ, 430), "p", "Spec review #430", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(430, "spec")
        (ap.cache / "skills" / "dispositions-430.jsonl").unlink()
        ap.harvest()
        assert ap.rows()["skills/430/spec/1/findings-spec-430"]["status"]["mappings"] == \
            [{"from": "partial", "to": "fixed+partial"}]

    def shared_pair(self, ap):
        write_jsonl(ap.cache / "skills" / "findings-standards-420.jsonl",
                    [finding("S1", "hard", "a.py", "Duplicated loader helper")])
        write_jsonl(ap.cache / "skills" / "findings-spec-420.jsonl",
                    [finding("P1", "hard", "a.py", "loader helper duplicated", axis="spec")])
        for axis, agent in (("Standards", "s"), ("Spec", "p")):
            transcript(ap.tr, wt(SKILLS_PROJ, 420), agent, f"{axis} review #420", "Repo: x",
                       [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])

    def test_a_harvest_after_one_reviewers_sidecar_is_pruned_keeps_the_shared_credit(self, ap):
        self.shared_pair(ap)
        ap.ok(420, "standards")
        ap.ok(420, "spec")
        (ap.cache / "skills" / "findings-standards-420.jsonl").unlink()
        ap.harvest()
        (p1,) = ap.rows()["skills/420/spec/1/findings-spec-420"]["findings"]
        assert (p1["overlap"], p1["k"]) == ("shared", 2)

    def test_a_harvest_reports_the_credit_it_re_split_and_counts_only_rows_it_wrote(self, ap):
        self.shared_pair(ap)
        ap.ok(420, "standards")
        ap.ok(420, "spec")
        (ap.cache / "skills" / "findings-standards-420.jsonl").unlink()
        # A fresh harvest also writes the standards transcript as a row of its own; this one holds it already.
        written = len(ap.harvested()) - 1
        out = ap.harvest().stdout
        assert f"harvested {written} rows" in out
        matches = (ap.tmp / "h.md").read_text().split("## Overlap matches")[1].split("\n## ")[0]
        assert '#420 `a.py`' in matches

    def test_other_rows_in_the_ledger_are_kept(self, ap):
        write_jsonl(ap.ledger, [{"row_id": "keep", "origin": "harvest", "type": "spec"}])
        ap.ok(403, "verification")
        assert "keep" in ap.rows()

    def test_overlap_is_recomputed_across_the_ticket_as_each_reviewer_appends(self, ap):
        self.shared_pair(ap)
        ap.ok(420, "standards")
        assert ap.rows()["skills/420/standards/1/findings-standards-420"]["findings"][0]["overlap"] == "unique"
        ap.ok(420, "spec")
        assert len(ap.rows()) == 2
        for row in ap.rows().values():
            assert (row["findings"][0]["overlap"], row["findings"][0]["k"]) == ("shared", 2)

    def test_the_verification_append_fills_the_outcomes_of_the_rounds_axis_rows(self, ap):
        # The axes append before dispositions exist; the verification pass writes them, then appends.
        skills = ap.cache / "skills"
        write_jsonl(skills / "findings-standards-430.jsonl", [finding("S1", "hard", "a.py", "Early thing")])
        transcript(ap.tr, wt(SKILLS_PROJ, 430), "s", "Standards review #430", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(430, "standards")
        row_id = "skills/430/standards/1/findings-standards-430"
        assert ap.rows()[row_id]["findings"][0]["outcome"] == "unknown"
        cost = ap.rows()[row_id]["cost"]
        # A round-2 axis row of the same ticket is not this verification's round.
        write_jsonl(skills / "findings-standards-430-r2.jsonl", [finding("r2-S1", "hard", "b.py", "Later thing")])
        transcript(ap.tr, wt(SKILLS_PROJ, 430), "s2", "Standards review round-2 #430", "Repo: x",
                   [("2026-09-20T10:30:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(430, "standards", 2)
        write_jsonl(skills / "dispositions-430.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"},
                                                        {"id": "r2-S1", "outcome": "fixed", "sha": "e"}])
        write_jsonl(skills / "findings-verify-430.jsonl", [])
        transcript(ap.tr, wt(SKILLS_PROJ, 430), "v", "Verification pass", "Verification of round 1",
                   [("2026-09-20T11:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(430, "verification")
        row = ap.rows()[row_id]
        assert row["findings"][0]["outcome"] == "fixed"
        assert "skills/dispositions-430.jsonl" in row["status"]["sources"]
        assert row["cost"] == cost
        assert row["origin"] == "append"
        later = ap.rows()["skills/430/standards/2/findings-standards-430-r2"]
        assert later["findings"][0]["outcome"] == "unknown"

    def test_the_verification_append_adds_no_axis_row_that_was_never_appended(self, ap):
        ap.ok(400, "standards")
        write_jsonl(ap.cache / "skills" / "findings-verify-400.jsonl", [])
        transcript(ap.tr, wt(SKILLS_PROJ, 400), "v", "Verification pass", "Verification of round 1",
                   [("2026-09-20T11:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(400, "verification")
        assert sorted(ap.rows()) == [
            "skills/400/over-engineering/1/findings-standards-400",
            "skills/400/standards/1/findings-standards-400",
            "skills/400/verification/1/findings-verify-400"]

    def hold_ledger_lock(self, ap, request):
        """Take the ledger's lock the way a writer does; the test's own process is the writer in progress."""
        lock = open(ap.ledger.with_name(ap.ledger.name + ".lock"), "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
        request.addfinalizer(lock.close)
        return lock

    def assert_blocks_until_released(self, ap, request, args, lock):
        """A command that writes the ledger waits for the lock: still running while it is held, done after."""
        proc = subprocess.Popen([sys.executable, str(SCRIPT), *map(str, args)], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=dict(os.environ, HOME=str(ap.home)))
        request.addfinalizer(proc.kill)
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=3)  # a finished run here wrote the ledger without the lock
        fcntl.flock(lock, fcntl.LOCK_UN)
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err

    def test_an_append_waits_for_the_ledger_lock(self, ap, request):
        lock = self.hold_ledger_lock(ap, request)
        self.assert_blocks_until_released(
            ap, request,
            ["append", "--repo", "skills", "--ticket", 403, "--type", "verification", "--cache", ap.cache,
             "--transcripts", ap.tr, "--ledger", ap.ledger], lock)
        assert len(ap.rows()) == 1

    def test_a_harvest_waits_for_the_ledger_lock(self, ap, request):
        lock = self.hold_ledger_lock(ap, request)
        self.assert_blocks_until_released(
            ap, request,
            ["harvest", "--cache", ap.cache, "--transcripts", ap.tr, "--ledger", ap.ledger,
             "--review-file", ap.tmp / "h.md"], lock)
        assert sorted(ap.rows()) == sorted(ap.harvested())

    def test_parallel_appends_by_the_three_axes_all_land(self, ap):
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(lambda t: ap.append(400, t), ("standards", "spec", "correctness")))
        assert {r.returncode for r in results} == {0}, [r.stderr for r in results]
        assert len(ap.rows()) == 4

    def test_a_clean_later_round_with_an_empty_sidecar_appends_under_its_own_round(self, ap):
        (ap.cache / "skills" / "findings-standards-430-r2.jsonl").write_text("")
        transcript(ap.tr, wt(SKILLS_PROJ, 430), "c2", "Standards review round-2 #430", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(430, "standards", 2)
        assert [r["round"] for r in ap.rows().values()] == [2]

    def test_a_foreign_row_of_the_same_ticket_is_not_rescored_and_does_not_crash_the_append(self, ap):
        foreign = {"row_id": "skills/403/witness-mutation/1/x", "origin": "append", "repo": "skills", "ticket": 403,
                   "type": "witness-mutation", "findings": [{"id": "m1", "overlap": "unique", "k": 1}]}
        write_jsonl(ap.ledger, [foreign])
        ap.ok(403, "verification")
        assert ap.rows()[foreign["row_id"]] == foreign

    def test_another_ticket_spoken_to_from_the_primary_checkout_is_not_appended(self, ap):
        transcript(ap.tr, SKILLS_PROJ, "xt", "Standards review #402 extra", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        ap.ok(400, "standards")
        assert {r["ticket"] for r in ap.rows().values()} == {400}


class TestAppendUnknownCost:
    """#1374: a review axis whose cost cannot be attributed is recorded with the cost unknown."""

    def cost(self, ap, ticket, rtype="standards"):
        ap.ok(ticket, rtype)
        return next(r for r in ap.rows().values() if r["type"] == rtype)["cost"]

    def test_an_axis_run_with_no_transcript_is_recorded_with_unknown_tokens(self, ap):
        tokens = self.cost(ap, 401)["tokens"]
        assert tokens["status"] == "unknown"
        assert "no transcript" in tokens["reason"]

    def test_a_transcript_with_no_usage_is_recorded_with_unknown_tokens(self, ap):
        tokens = self.cost(ap, 402)["tokens"]
        assert tokens["status"] == "unknown"
        assert "usage" in tokens["reason"]

    def test_known_tokens_with_unreadable_wall_clock_keeps_the_tokens_and_marks_the_clock(self, ap):
        cost = self.cost(ap, 418)
        assert cost["tokens"]["status"] == "known"
        assert cost["wall_clock"]["status"] == "unknown"
        assert "timestamp" in cost["wall_clock"]["reason"]

    @pytest.mark.parametrize("axis, letter", [("spec", "P"), ("correctness", "C")])
    def test_spec_and_correctness_rows_with_no_transcript_are_recorded_too(self, ap, axis, letter):
        write_jsonl(ap.cache / "skills" / f"findings-{axis}-408.jsonl",
                    [finding(f"{letter}1", "hard", "a.py", "Thing 408", axis=axis)])
        assert self.cost(ap, 408, axis)["tokens"]["status"] == "unknown"

    def test_report_counts_the_row_as_a_run_review_with_unknown_cost_not_zero(self, ap):
        ap.ok(401, "standards")
        r = ap.run("report", "--ledger", ap.ledger, "--format", "json")
        assert r.returncode == 0, r.stderr
        std = next(t for t in json.loads(r.stdout)["types"] if t["type"] == "standards")
        assert (std["rows"], std["unknown_cost_rows"], std["skipped_rows"]) == (1, 1, None)
        assert std["tokens"] is None
        assert std["wall_clock_seconds"] is None


class TestAppendRefusal:
    def assert_refused(self, ap, r, *needles):
        assert r.returncode == 2, r.stdout + r.stderr
        for n in needles:
            assert n in r.stderr
        assert ap.rows() == {}

    def test_a_round_the_ticket_has_no_sidecar_for_is_refused(self, ap):
        self.assert_refused(ap, ap.append(404, "standards", 1), "findings sidecar", "round 1")

    def test_a_verification_run_with_an_unattributed_cost_is_still_refused(self, ap):
        write_jsonl(ap.cache / "skills" / "findings-verification-407.jsonl", [])
        self.assert_refused(ap, ap.append(407, "verification"), "tokens", "no transcript")

    def test_a_missing_transcripts_tree_is_refused(self, ap):
        self.assert_refused(ap, ap.append(400, "standards", tr=ap.tmp / "absent"), "transcripts tree not found")

    def test_the_default_transcripts_tree_missing_is_refused_naming_it(self, ap):
        r = ap.run("append", "--repo", "skills", "--ticket", 400, "--type", "standards", "--cache", ap.cache,
                   "--ledger", ap.ledger)
        self.assert_refused(ap, r, "transcripts tree not found")

    def test_a_missing_findings_sidecar_is_refused_naming_it(self, ap):
        self.assert_refused(ap, ap.append(999, "standards"), "findings sidecar", "standards", "#999")

    def test_a_sidecar_for_another_type_does_not_satisfy_the_append(self, ap):
        self.assert_refused(ap, ap.append(405, "standards"), "findings sidecar")

    def test_a_run_with_a_transcript_and_no_sidecar_is_refused(self, ap):
        self.assert_refused(ap, ap.append(406, "verification"), "findings sidecar")

    def test_a_missing_cache_is_refused(self, ap):
        self.assert_refused(ap, ap.append(400, "standards", cache=ap.tmp / "absent"), "absent")

    def test_a_corrupt_ledger_is_refused_and_left_alone(self, ap):
        ap.ledger.write_text("not json\n")
        r = ap.append(403, "verification")
        assert r.returncode == 2
        assert ap.ledger.read_text() == "not json\n"

    def test_a_type_outside_append_choices_is_refused(self, ap):
        self.assert_refused(ap, ap.append(400, "not-a-ledger-type"), "invalid choice: 'not-a-ledger-type'")
