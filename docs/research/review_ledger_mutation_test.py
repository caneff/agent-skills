#!/usr/bin/env python3
"""Tests for the mutation rows of `review_ledger.py` (#1270): `append` fed witness-check
status files, and the mutation columns of `report`. Every test runs the command line;
HOME is a temp dir, so no default path reaches the real ~/.cache or ~/.claude."""
import json
import unittest

from review_ledger_test import Case, finding, run, write_jsonl


class MutationCase(Case):
    def setUp(self):
        super().setUp()
        self.ledger = self.tmp / "ledger.jsonl"
        self.status = self.tmp / "status"
        self.status.mkdir()

    def status_file(self, mutation_id, text):
        (self.status / mutation_id).write_text(text)
        return self.status / mutation_id

    def append(self, mutation_id, rtype="witness-mutation", status="red\n", seconds=12, ticket=500):
        path = self.status_file(mutation_id, status) if status is not None else self.status / mutation_id
        return run("append", "--repo", "skills", "--ticket", ticket, "--type", rtype, "--mutation-id",
                   mutation_id, "--status-file", path, "--seconds", seconds, "--ledger", self.ledger,
                   home=self.home)

    def ok(self, *a, **k):
        r = self.append(*a, **k)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def rows(self):
        return {r["row_id"]: r for r in map(json.loads, self.ledger.read_text().splitlines())} \
            if self.ledger.exists() else {}


class AppendMutationTest(MutationCase):
    def test_one_row_per_mutation_id_with_its_outcome_and_wall_clock(self):
        self.ok("m1", status="red\n", seconds=12)
        self.ok("m2", status="green\n", seconds=7)
        self.ok("m3", status="unknown\n", seconds=0)
        got = {r["mutation_id"]: (r["outcome"], r["cost"]["wall_clock"]["seconds"]) for r in self.rows().values()}
        self.assertEqual(got, {"m1": ("red", 12), "m2": ("green", 7), "m3": ("unknown", 0)})
        self.assertEqual({r["type"] for r in self.rows().values()}, {"witness-mutation"})

    def test_unknown_stays_unknown(self):
        self.ok("m1", status="unknown\n")
        self.assertEqual(next(iter(self.rows().values()))["outcome"], "unknown")

    def test_an_empty_or_malformed_status_is_unknown_never_red_or_green(self):
        for i, text in enumerate(["", "\n", "RED?\n", "redgreen\n", "-1\n", "1 0\n", "1\n", "0\n", "127\n"]):
            self.ok(f"m{i}", status=text)
            self.assertEqual(self.rows()[f"skills/500/witness-mutation/1/m{i}"]["outcome"], "unknown", repr(text))

    def test_call_site_and_worker_types_append_too(self):
        self.ok("c1", "call-site-mutation", "red\n")
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "worker-mutation", "--mutation-id", "w1",
                "--outcome", "green", "--seconds", 30, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(r["type"] for r in self.rows().values()), ["call-site-mutation", "worker-mutation"])

    def test_the_same_mutation_twice_leaves_one_row(self):
        self.ok("m1", status="green\n")
        self.ok("m1", status="red\n")
        self.assertEqual([r["outcome"] for r in self.rows().values()], ["red"])

    def test_a_later_harvest_keeps_mutation_rows(self):
        self.ok("m1")
        cache = self.tmp / "cache"
        write_jsonl(cache / "skills" / "findings-spec-900.jsonl", [finding("P1", "hard", "a.py", "x", axis="spec")])
        r = run("harvest", "--cache", cache, "--transcripts", self.tmp, "--ledger", self.ledger,
                "--review-file", self.tmp / "h.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skills/500/witness-mutation/1/m1", self.rows())
        self.assertEqual(len(self.rows()), 2)

    def test_a_missing_status_file_is_refused_and_writes_nothing(self):
        r = self.append("m1", status=None)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(self.ledger.exists())

    def test_a_bad_wall_clock_is_refused(self):
        for bad in ("-3", "soon", "nan", "inf"):
            self.assertEqual(self.append("m1", seconds=bad).returncode, 2, bad)
        self.assertFalse(self.ledger.exists())

    def test_the_outcome_source_is_exactly_one_of_status_file_and_outcome(self):
        base = ["append", "--repo", "skills", "--ticket", 500, "--type", "worker-mutation", "--mutation-id", "w1",
                "--seconds", 5, "--ledger", self.ledger]
        self.assertEqual(run(*base, home=self.home).returncode, 2)
        both = run(*base, "--outcome", "red", "--status-file", self.status_file("w1", "red"), home=self.home)
        self.assertEqual(both.returncode, 2)
        self.assertEqual(run(*base, "--outcome", "maybe", home=self.home).returncode, 2)
        self.assertFalse(self.ledger.exists())

    def test_a_mutation_append_without_an_id_or_with_an_unusable_one_is_refused(self):
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation", "--outcome", "red",
                "--seconds", 1, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 2)
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation",
                "--mutation-id", "tests/a.py::t1", "--outcome", "red", "--seconds", 1, "--ledger", self.ledger,
                home=self.home)
        self.assertEqual(r.returncode, 2)
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation",
                "--mutation-id", "m1\n", "--outcome", "red", "--seconds", 1, "--ledger", self.ledger,
                home=self.home)
        self.assertEqual(r.returncode, 2)  # a trailing newline is not an id character
        self.assertFalse(self.ledger.exists())

    def test_a_review_type_refuses_mutation_arguments(self):
        r = run("append", "--repo", "skills", "--ticket", 500, "--type", "standards", "--mutation-id", "m1",
                "--outcome", "red", "--seconds", 1, "--ledger", self.ledger, home=self.home)
        self.assertEqual(r.returncode, 2)
        self.assertIn("are for mutation types", r.stderr)  # the guard's own message, not a missing transcripts tree

    def test_a_mutation_type_refuses_the_review_cache_arguments(self):
        for flag in ("--cache", "--transcripts"):
            r = run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation", "--mutation-id",
                    "m1", "--outcome", "red", "--seconds", 1, flag, self.tmp, "--ledger", self.ledger,
                    home=self.home)
            self.assertEqual(r.returncode, 2, flag)
            self.assertIn("are for review types", r.stderr)
        self.assertFalse(self.ledger.exists())

    def test_a_corrupt_ledger_is_refused_and_left_alone(self):
        self.ledger.write_text("not json\n")
        self.assertEqual(self.append("m1").returncode, 2)
        self.assertEqual(self.ledger.read_text(), "not json\n")


class ReportMutationTest(MutationCase):
    def report(self, fmt="json"):
        r = run("report", "--ledger", self.ledger, "--format", fmt, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def types(self):
        return {t["type"]: t for t in json.loads(self.report())["types"]}

    def test_red_rate_unknown_count_and_wall_clock_per_mutation_type(self):
        for i, (s, secs) in enumerate([("red", 10), ("red", 20), ("green", 30), ("unknown", 40)]):
            self.ok(f"m{i}", status=f"{s}\n", seconds=secs)
        t = self.types()["witness-mutation"]
        self.assertEqual((t["rows"], t["unknown_mutations"], t["wall_clock_seconds"]), (4, 1, 100))
        self.assertAlmostEqual(t["red_rate"], 2 / 3)  # the unknown is left out of the rate, not counted red
        self.assertEqual(t["unknown_cost_rows"], 0)
        self.assertEqual(t["unknown_finding_rows"], 0)

    def test_only_unknown_mutations_have_no_red_rate(self):
        self.ok("m1", status="unknown\n")
        t = self.types()["witness-mutation"]
        self.assertIsNone(t["red_rate"])
        self.assertEqual(t["unknown_mutations"], 1)

    def test_a_review_type_has_no_mutation_columns(self):
        self.ok("m1")
        self.assertNotIn("standards", self.types())
        table = self.report("md")
        self.assertIn("red rate", table)
        self.assertIn("| witness-mutation | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 |", table)

    def test_a_mutation_type_shows_no_finding_counts_rather_than_zero(self):
        self.ok("m1")
        t = self.types()["witness-mutation"]
        self.assertEqual([t[k] for k in ("findings", "value", "unknown_outcomes", "unweighted")], [None] * 4)

    def test_the_report_says_outright_that_past_reviews_carry_no_mutation_data(self):
        self.ok("m1")
        self.assertIn("Reviews before #1270 carry no mutation data", self.report("md"))
        self.assertIn("Reviews before #1270 carry no mutation data", " ".join(json.loads(self.report())["notes"]))


if __name__ == "__main__":
    unittest.main()
