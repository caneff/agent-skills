#!/usr/bin/env python3
"""Tests for `review_ledger.py append` (#1268). Every test runs the command line on
the fixture trees `review_ledger_test.py` builds and reads the ledger it leaves;
HOME is a temp dir, so no default path reaches the real ~/.cache or ~/.claude."""
import fcntl
import json
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from review_ledger_test import (SCRIPT, SKILLS_PROJ, Case, build_cost_fixture, finding, run, transcript, usage,
                                write_jsonl, wt)


class AppendCase(Case):
    def setUp(self):
        super().setUp()
        self.cache, self.tr = build_cost_fixture(self.tmp)
        self.ledger = self.tmp / "ledger.jsonl"

    def append(self, ticket, rtype, rnd=1, repo="skills", cache=None, tr=None):
        return run("append", "--repo", repo, "--ticket", ticket, "--type", rtype, "--round", rnd,
                   "--cache", cache or self.cache, "--transcripts", tr or self.tr, "--ledger", self.ledger,
                   home=self.home)

    def ok(self, *a, **k):
        r = self.append(*a, **k)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def rows(self):
        return {r["row_id"]: r for r in map(json.loads, self.ledger.read_text().splitlines())} \
            if self.ledger.exists() else {}

    def harvested(self):
        other = self.tmp / "harvested.jsonl"
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", other,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {r["row_id"]: r for r in map(json.loads, other.read_text().splitlines())}


class AppendRowTest(AppendCase):
    def test_a_later_append_keeps_a_claude_and_codex_finding_shared_on_both_sides(self):
        skills = self.cache / "skills"
        (skills / "codex-adversarial-400-gate.json").write_text(json.dumps({
            "ticket": 400, "phase": "gate", "status": 0, "started": "2026-09-22T09:00:00-04:00",
            "completed": "2026-09-22T09:01:00-04:00"}))
        (skills / "codex-adversarial-400-gate.out").write_text(
            "Findings:\n- [high] Thing 400 (a.py:1)\n  Body.\n\nNext steps:\n- Fix.\n")
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.ok(400, "standards")
        rows = self.rows()
        codex = rows["skills/400/codex-gate/1/codex-adversarial-400-gate"]["findings"][0]
        std = next(f for f in rows["skills/400/standards/1/findings-standards-400"]["findings"] if f["id"] == "S1")
        self.assertEqual((codex["overlap"], codex["k"]), ("shared", 2))
        self.assertEqual((std["overlap"], std["k"]), ("shared", 2))

    def test_writes_the_row_harvest_writes_for_the_same_inputs(self):
        self.ok(400, "standards")
        self.ok(400, "spec")
        self.ok(400, "correctness")
        want = self.harvested()
        got = self.rows()
        self.assertEqual(len(got), 4)  # standards, over-engineering, spec, correctness
        for row_id, row in got.items():
            self.assertEqual(row["origin"], "append")
            self.assertEqual({**row, "origin": "harvest"}, want[row_id], row_id)

    def test_a_standards_append_writes_the_over_engineering_row_with_cost_inside_standards(self):
        self.ok(400, "standards")
        oe = self.rows()["skills/400/over-engineering/1/findings-standards-400"]
        self.assertEqual(oe["cost"]["tokens"]["status"], "inside-standards")
        self.assertEqual(len(self.rows()), 2)

    def test_the_verification_pass_and_a_later_round_append_too(self):
        self.ok(403, "verification")
        self.ok(404, "standards", 2)
        self.assertEqual(sorted(self.rows()), [
            "skills/403/verification/1/findings-verify-403",
            "skills/404/standards/2/findings-standards-404-r2"])

    def test_appending_the_same_run_twice_leaves_one_row(self):
        self.ok(403, "verification")
        first = self.ledger.read_text()
        self.ok(403, "verification")
        self.assertEqual(self.ledger.read_text(), first)
        self.assertEqual(len(first.splitlines()), 1)

    def test_a_later_harvest_leaves_exactly_the_rows_a_harvest_alone_writes(self):
        self.ok(403, "verification")
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(self.rows()), sorted(self.harvested()))

    def test_other_rows_in_the_ledger_are_kept(self):
        write_jsonl(self.ledger, [{"row_id": "keep", "origin": "harvest", "type": "spec"}])
        self.ok(403, "verification")
        self.assertIn("keep", self.rows())

    def test_overlap_is_recomputed_across_the_ticket_as_each_reviewer_appends(self):
        write_jsonl(self.cache / "skills" / "findings-standards-420.jsonl",
                    [finding("S1", "hard", "a.py", "Duplicated loader helper")])
        write_jsonl(self.cache / "skills" / "findings-spec-420.jsonl",
                    [finding("P1", "hard", "a.py", "loader helper duplicated", axis="spec")])
        for axis, agent in (("Standards", "s"), ("Spec", "p")):
            transcript(self.tr, wt(SKILLS_PROJ, 420), agent, f"{axis} review #420", "Repo: x",
                       [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(420, "standards")
        self.assertEqual(self.rows()["skills/420/standards/1/findings-standards-420"]["findings"][0]["overlap"],
                         "unique")
        self.ok(420, "spec")
        for row in self.rows().values():
            self.assertEqual((row["findings"][0]["overlap"], row["findings"][0]["k"]), ("shared", 2))

    def test_the_verification_append_fills_the_outcomes_of_the_rounds_axis_rows(self):
        # The axes append before dispositions exist; the verification pass writes them, then appends.
        skills = self.cache / "skills"
        write_jsonl(skills / "findings-standards-430.jsonl", [finding("S1", "hard", "a.py", "Early thing")])
        transcript(self.tr, wt(SKILLS_PROJ, 430), "s", "Standards review #430", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(430, "standards")
        row_id = "skills/430/standards/1/findings-standards-430"
        self.assertEqual(self.rows()[row_id]["findings"][0]["outcome"], "unknown")
        cost = self.rows()[row_id]["cost"]
        write_jsonl(skills / "dispositions-430.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"}])
        write_jsonl(skills / "findings-verify-430.jsonl", [])
        transcript(self.tr, wt(SKILLS_PROJ, 430), "v", "Verification pass", "Verification of round 1",
                   [("2026-09-20T11:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(430, "verification")
        row = self.rows()[row_id]
        self.assertEqual(row["findings"][0]["outcome"], "fixed")
        self.assertIn("skills/dispositions-430.jsonl", row["status"]["sources"])
        self.assertEqual(row["cost"], cost)
        self.assertEqual(row["origin"], "append")

    def test_the_verification_append_adds_no_axis_row_that_was_never_appended(self):
        self.ok(400, "standards")
        write_jsonl(self.cache / "skills" / "findings-verify-400.jsonl", [])
        transcript(self.tr, wt(SKILLS_PROJ, 400), "v", "Verification pass", "Verification of round 1",
                   [("2026-09-20T11:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(400, "verification")
        self.assertEqual(sorted(self.rows()), [
            "skills/400/over-engineering/1/findings-standards-400",
            "skills/400/standards/1/findings-standards-400",
            "skills/400/verification/1/findings-verify-400"])

    def hold_ledger_lock(self):
        """Take the ledger's lock the way a writer does; the test's own process is the writer in progress."""
        lock = open(self.ledger.with_name(self.ledger.name + ".lock"), "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
        self.addCleanup(lock.close)
        return lock

    def assert_blocks_until_released(self, args, lock):
        """A command that writes the ledger waits for the lock: still running while it is held, done after."""
        proc = subprocess.Popen([sys.executable, str(SCRIPT), *map(str, args)], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=dict(os.environ, HOME=str(self.home)))
        self.addCleanup(proc.kill)
        with self.assertRaises(subprocess.TimeoutExpired):
            proc.wait(timeout=3)  # a finished run here wrote the ledger without the lock
        fcntl.flock(lock, fcntl.LOCK_UN)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)

    def test_an_append_waits_for_the_ledger_lock(self):
        lock = self.hold_ledger_lock()
        self.assert_blocks_until_released(
            ["append", "--repo", "skills", "--ticket", 403, "--type", "verification", "--cache", self.cache,
             "--transcripts", self.tr, "--ledger", self.ledger], lock)
        self.assertEqual(len(self.rows()), 1)

    def test_a_harvest_waits_for_the_ledger_lock(self):
        lock = self.hold_ledger_lock()
        self.assert_blocks_until_released(
            ["harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
             "--review-file", self.tmp / "h.md"], lock)
        self.assertEqual(sorted(self.rows()), sorted(self.harvested()))

    def test_parallel_appends_by_the_three_axes_all_land(self):
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(lambda t: self.append(400, t), ("standards", "spec", "correctness")))
        self.assertEqual({r.returncode for r in results}, {0}, [r.stderr for r in results])
        self.assertEqual(len(self.rows()), 4)

    def test_a_clean_later_round_with_an_empty_sidecar_appends_under_its_own_round(self):
        (self.cache / "skills" / "findings-standards-430-r2.jsonl").write_text("")
        transcript(self.tr, wt(SKILLS_PROJ, 430), "c2", "Standards review round-2 #430", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(430, "standards", 2)
        self.assertEqual([r["round"] for r in self.rows().values()], [2])

    def test_a_foreign_row_of_the_same_ticket_is_not_rescored_and_does_not_crash_the_append(self):
        foreign = {"row_id": "skills/403/witness-mutation/1/x", "origin": "append", "repo": "skills", "ticket": 403,
                   "type": "witness-mutation", "findings": [{"id": "m1", "overlap": "unique", "k": 1}]}
        write_jsonl(self.ledger, [foreign])
        self.ok(403, "verification")
        self.assertEqual(self.rows()[foreign["row_id"]], foreign)

    def test_another_ticket_spoken_to_from_the_primary_checkout_is_not_appended(self):
        transcript(self.tr, SKILLS_PROJ, "xt", "Standards review #402 extra", "Repo: x",
                   [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(400, "standards")
        self.assertEqual({r["ticket"] for r in self.rows().values()}, {400})


class AppendRefusalTest(AppendCase):
    def assert_refused(self, r, *needles):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        for n in needles:
            self.assertIn(n, r.stderr)
        self.assertEqual(self.rows(), {})

    def test_a_transcript_with_no_usage_is_refused_not_written_as_zero_cost(self):
        self.assert_refused(self.append(402, "standards"), "tokens", "usage")

    def test_an_axis_run_with_no_transcript_is_refused_not_written_as_zero_cost(self):
        self.assert_refused(self.append(401, "standards"), "tokens", "no transcript")

    def test_a_round_the_ticket_has_no_sidecar_for_is_refused(self):
        self.assert_refused(self.append(404, "standards", 1), "findings sidecar", "round 1")

    def test_known_tokens_with_unreadable_wall_clock_is_still_refused(self):
        self.assert_refused(self.append(418, "standards"), "wall_clock", "timestamp")

    def test_a_missing_transcripts_tree_is_refused(self):
        self.assert_refused(self.append(400, "standards", tr=self.tmp / "absent"), "transcripts tree not found")

    def test_the_default_transcripts_tree_missing_is_refused_naming_it(self):
        r = run("append", "--repo", "skills", "--ticket", 400, "--type", "standards", "--cache", self.cache,
                "--ledger", self.ledger, home=self.home)
        self.assert_refused(r, "transcripts tree not found")

    def test_a_missing_findings_sidecar_is_refused_naming_it(self):
        self.assert_refused(self.append(999, "standards"), "findings sidecar", "standards", "#999")

    def test_a_sidecar_for_another_type_does_not_satisfy_the_append(self):
        self.assert_refused(self.append(405, "standards"), "findings sidecar")

    def test_a_run_with_a_transcript_and_no_sidecar_is_refused(self):
        self.assert_refused(self.append(406, "verification"), "findings sidecar")

    def test_a_missing_cache_is_refused(self):
        self.assert_refused(self.append(400, "standards", cache=self.tmp / "absent"), "absent")

    def test_a_corrupt_ledger_is_refused_and_left_alone(self):
        self.ledger.write_text("not json\n")
        r = self.append(403, "verification")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.ledger.read_text(), "not json\n")

    def test_a_type_outside_the_reviewer_list_is_refused(self):
        r = self.append(400, "worker-mutation")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
