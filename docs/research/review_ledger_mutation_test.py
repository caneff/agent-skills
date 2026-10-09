"""Tests for the mutation rows of `review_ledger.py` (#1270): `append` fed witness-check
status files, and the mutation columns of `report`. Every test runs the command line;
HOME is a temp dir, so no default path reaches the real ~/.cache or ~/.claude."""
import json

import pytest

from review_ledger_support import Env, finding, report_rows, write_jsonl


class Mutations(Env):
    """The status-file directory of one test and the `append` commands that read it."""

    def __init__(self, tmp):
        super().__init__(tmp)
        self.status = tmp / "status"
        self.status.mkdir()

    def status_file(self, mutation_id, text):
        (self.status / mutation_id).write_text(text)
        return self.status / mutation_id

    def append(self, mutation_id, rtype="witness-mutation", status="red\n", seconds=12, ticket=500):
        path = self.status_file(mutation_id, status) if status is not None else self.status / mutation_id
        return self.run("append", "--repo", "skills", "--ticket", ticket, "--type", rtype, "--mutation-id",
                        mutation_id, "--status-file", path, "--seconds", seconds, "--ledger", self.ledger)

    def ok(self, *a, **k):
        r = self.append(*a, **k)
        assert r.returncode == 0, r.stderr
        return r


@pytest.fixture
def mut(tmp_path):
    return Mutations(tmp_path)


class TestAppendMutation:
    def test_one_row_per_mutation_id_with_its_outcome_and_wall_clock(self, mut):
        mut.ok("m1", status="red\n", seconds=12)
        mut.ok("m2", status="green\n", seconds=7)
        mut.ok("m3", status="unknown\n", seconds=0)
        got = {r["mutation_id"]: (r["outcome"], r["cost"]["wall_clock"]["seconds"]) for r in mut.rows().values()}
        assert got == {"m1": ("red", 12), "m2": ("green", 7), "m3": ("unknown", 0)}
        assert {r["type"] for r in mut.rows().values()} == {"witness-mutation"}

    def test_an_empty_or_malformed_status_is_unknown_never_red_or_green(self, mut):
        for i, text in enumerate(["", "\n", "RED?\n", "redgreen\n", "-1\n", "1 0\n", "1\n", "0\n", "127\n"]):
            mut.ok(f"m{i}", status=text)
            assert mut.rows()[f"skills/500/witness-mutation/1/m{i}"]["outcome"] == "unknown", repr(text)

    def test_call_site_and_worker_types_append_too(self, mut):
        mut.ok("c1", "call-site-mutation", "red\n")
        r = mut.run("append", "--repo", "skills", "--ticket", 500, "--type", "worker-mutation", "--mutation-id", "w1",
                    "--outcome", "green", "--seconds", 30, "--ledger", mut.ledger)
        assert r.returncode == 0, r.stderr
        assert sorted(r["type"] for r in mut.rows().values()) == ["call-site-mutation", "worker-mutation"]

    def test_the_same_mutation_twice_leaves_one_row(self, mut):
        mut.ok("m1", status="green\n")
        mut.ok("m1", status="red\n")
        assert [r["outcome"] for r in mut.rows().values()] == ["red"]

    def test_a_later_harvest_keeps_mutation_rows(self, mut):
        mut.ok("m1")
        cache = mut.tmp / "cache"
        write_jsonl(cache / "skills" / "findings-spec-900.jsonl", [finding("P1", "hard", "a.py", "x", axis="spec")])
        r = mut.run("harvest", "--cache", cache, "--transcripts", mut.tmp, "--ledger", mut.ledger,
                    "--review-file", mut.tmp / "h.md")
        assert r.returncode == 0, r.stderr
        assert "skills/500/witness-mutation/1/m1" in mut.rows()
        assert len(mut.rows()) == 2

    def test_a_missing_status_file_is_refused_and_writes_nothing(self, mut):
        r = mut.append("m1", status=None)
        assert r.returncode == 2
        assert not mut.ledger.exists()

    @pytest.mark.parametrize("bad", ["-3", "soon", "nan", "inf"])
    def test_a_bad_wall_clock_is_refused(self, mut, bad):
        assert mut.append("m1", seconds=bad).returncode == 2, bad
        assert not mut.ledger.exists()

    def test_the_outcome_source_is_exactly_one_of_status_file_and_outcome(self, mut):
        base = ["append", "--repo", "skills", "--ticket", 500, "--type", "worker-mutation", "--mutation-id", "w1",
                "--seconds", 5, "--ledger", mut.ledger]
        assert mut.run(*base).returncode == 2
        both = mut.run(*base, "--outcome", "red", "--status-file", mut.status_file("w1", "red"))
        assert both.returncode == 2
        assert mut.run(*base, "--outcome", "maybe").returncode == 2
        assert not mut.ledger.exists()

    @pytest.mark.parametrize("id_args", [
        [],
        ["--mutation-id", "tests/a.py::t1"],
        ["--mutation-id", "m1\n"],  # a trailing newline is not an id character
    ])
    def test_a_mutation_append_without_an_id_or_with_an_unusable_one_is_refused(self, mut, id_args):
        r = mut.run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation", *id_args,
                    "--outcome", "red", "--seconds", 1, "--ledger", mut.ledger)
        assert r.returncode == 2
        assert not mut.ledger.exists()

    def test_a_review_type_refuses_mutation_arguments(self, mut):
        r = mut.run("append", "--repo", "skills", "--ticket", 500, "--type", "standards", "--mutation-id", "m1",
                    "--outcome", "red", "--seconds", 1, "--ledger", mut.ledger)
        assert r.returncode == 2
        # The parser's own message, not a missing transcripts tree.
        assert "append --type standards: error: unrecognized arguments: --mutation-id m1" in r.stderr

    @pytest.mark.parametrize("flag", ["--cache", "--transcripts"])
    def test_a_mutation_type_refuses_the_review_cache_arguments(self, mut, flag):
        r = mut.run("append", "--repo", "skills", "--ticket", 500, "--type", "witness-mutation", "--mutation-id",
                    "m1", "--outcome", "red", "--seconds", 1, flag, mut.tmp, "--ledger", mut.ledger)
        assert r.returncode == 2, flag
        assert f"unrecognized arguments: {flag}" in r.stderr
        assert not mut.ledger.exists()

    def test_a_corrupt_ledger_is_refused_and_left_alone(self, mut):
        mut.ledger.write_text("not json\n")
        assert mut.append("m1").returncode == 2
        assert mut.ledger.read_text() == "not json\n"


class TestReportMutation:
    def report(self, mut, fmt="json"):
        r = mut.run("report", "--ledger", mut.ledger, "--format", fmt)
        assert r.returncode == 0, r.stderr
        return r.stdout

    def types(self, mut):
        return {t["type"]: t for t in json.loads(self.report(mut))["types"]}

    def test_red_rate_unknown_count_and_wall_clock_per_mutation_type(self, mut):
        for i, (s, secs) in enumerate([("red", 10), ("red", 20), ("green", 30), ("unknown", 40)]):
            mut.ok(f"m{i}", status=f"{s}\n", seconds=secs)
        t = self.types(mut)["witness-mutation"]
        assert (t["rows"], t["unknown_mutations"], t["wall_clock_seconds"]) == (4, 1, 100)
        assert t["red_rate"] == pytest.approx(2 / 3)  # the unknown is left out of the rate, not counted red
        assert t["unknown_cost_rows"] == 0
        assert t["unknown_finding_rows"] == 0

    def test_only_unknown_mutations_have_no_red_rate(self, mut):
        mut.ok("m1", status="unknown\n")
        t = self.types(mut)["witness-mutation"]
        assert t["red_rate"] is None
        assert t["unknown_mutations"] == 1

    def test_a_review_type_has_no_mutation_columns(self, mut):
        mut.ok("m1")
        with mut.ledger.open("a") as f:
            f.write(json.dumps(report_rows()[0]) + "\n")
        review = self.types(mut)["standards"]
        assert review["red_rate"] is None
        assert review["unknown_mutations"] is None
        table = self.report(mut, "md")
        assert "red rate" in table
        assert "| witness-mutation | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 |" in table

    def test_a_mutation_type_shows_no_finding_counts_rather_than_zero(self, mut):
        mut.ok("m1")
        t = self.types(mut)["witness-mutation"]
        assert [t[k] for k in ("findings", "value", "unknown_outcomes", "unweighted")] == [None] * 4

    def test_the_report_says_outright_that_past_reviews_carry_no_mutation_data(self, mut):
        mut.ok("m1")
        assert "Reviews before #1270 carry no mutation data" in self.report(mut, "md")
        assert "Reviews before #1270 carry no mutation data" in " ".join(json.loads(self.report(mut))["notes"])
