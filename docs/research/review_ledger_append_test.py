#!/usr/bin/env python3
"""Tests for `review_ledger.py append` (#1268). Every test runs the command line on
the fixture trees `review_ledger_test.py` builds and reads the ledger it leaves;
HOME is a temp dir, so no default path reaches the real ~/.cache or ~/.claude."""
import json
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from review_ledger_test import (SKILLS_PROJ, Case, build_cost_fixture, finding, run, transcript, usage,
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

    def test_a_row_already_in_the_ledger_is_rewritten_not_duplicated_by_a_later_harvest(self):
        self.ok(403, "verification")
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [json.loads(l)["row_id"] for l in self.ledger.read_text().splitlines()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_other_rows_in_the_ledger_are_kept(self):
        write_jsonl(self.ledger, [{"row_id": "keep", "origin": "harvest", "type": "spec"}])
        self.ok(403, "verification")
        self.assertIn("keep", self.rows())

    def test_overlap_is_recomputed_across_the_ticket_as_each_reviewer_appends(self):
        write_jsonl(self.cache / "skills" / "findings-standards-420.jsonl",
                    [finding("S1", "hard", "a.py", "Duplicated loader helper")])
        write_jsonl(self.cache / "skills" / "findings-spec-420.jsonl",
                    [finding("P1", "hard", "a.py", "loader helper duplicated", axis="spec")])
        for n, (axis, agent) in enumerate((("Standards", "s"), ("Spec", "p"))):
            transcript(self.tr, wt(SKILLS_PROJ, 420), agent, f"{axis} review #420", "Repo: x",
                       [("2026-09-20T10:00:00Z", "m1", usage(1, 1, 1, 1))])
        self.ok(420, "standards")
        self.assertEqual(self.rows()["skills/420/standards/1/findings-standards-420"]["findings"][0]["overlap"],
                         "unique")
        self.ok(420, "spec")
        for row in self.rows().values():
            self.assertEqual((row["findings"][0]["overlap"], row["findings"][0]["k"]), ("shared", 2))

    def test_parallel_appends_by_the_three_axes_lose_no_row(self):
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(lambda t: self.append(400, t), ("standards", "spec", "correctness")))
        self.assertEqual([r.returncode for r in results], [0, 0, 0], [r.stderr for r in results])
        self.assertEqual(len(self.rows()), 4)


class AppendRefusalTest(AppendCase):
    def refused(self, r, *needles):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        for n in needles:
            self.assertIn(n, r.stderr)
        self.assertEqual(self.rows(), {})

    def test_a_transcript_with_no_usage_is_refused_not_written_as_zero_cost(self):
        self.refused(self.append(402, "standards"), "tokens", "usage")

    def test_an_axis_run_with_no_transcript_is_refused_not_written_as_zero_cost(self):
        self.refused(self.append(401, "standards"), "tokens", "no transcript")

    def test_a_missing_transcripts_tree_is_refused(self):
        self.refused(self.append(400, "standards", tr=self.tmp / "absent"), "transcripts tree not found")

    def test_the_default_transcripts_tree_missing_is_refused_naming_it(self):
        r = run("append", "--repo", "skills", "--ticket", 400, "--type", "standards", "--cache", self.cache,
                "--ledger", self.ledger, home=self.home)
        self.refused(r, "transcripts tree not found")

    def test_a_missing_findings_sidecar_is_refused_naming_it(self):
        self.refused(self.append(999, "standards"), "findings sidecar", "standards", "#999")

    def test_a_sidecar_for_another_type_does_not_satisfy_the_append(self):
        self.refused(self.append(405, "standards"), "findings sidecar")

    def test_a_run_with_a_transcript_and_no_sidecar_is_refused(self):
        self.refused(self.append(406, "verification"), "findings sidecar")

    def test_a_missing_cache_is_refused(self):
        self.refused(self.append(400, "standards", cache=self.tmp / "absent"), "absent")

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
