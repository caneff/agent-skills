#!/usr/bin/env python3
"""Tests for review_ledger.py (#1265). Every test runs a subcommand's command
line on a fixture tree and reads what comes out: ledger rows, the review file,
or the report. Nothing here calls the module's functions, and every run points
HOME at a temp dir so no default path can reach the real ~/.cache."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("review_ledger.py")


def write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def finding(fid, severity, file, title, axis="standards"):
    return {"id": fid, "axis": axis, "severity": severity, "file": file, "title": title}


def build_cache(root: Path) -> None:
    """The harvest fixture. Ticket 100 is one PR with three axes, an OE finding,
    two reviewers raising the same finding, every drifted outcome label and a
    disposition with no severity. 101 has a findings sidecar and no dispositions
    file. 102 is a verification pass. 103 sits under the alias repo directory."""
    skills = root / "skills"
    write_jsonl(skills / "findings-standards-100.jsonl", [
        finding("S1", "hard", "a.py", "Duplicated helper loader"),
        finding("S2", "judgement", "b.py", "Long function"),
        finding("OE1", "judgement", "c.py", "Unneeded wrapper class"),
    ])
    write_jsonl(skills / "findings-spec-100.jsonl", [
        finding("P1", "hard", "./a.py", "duplicated loader helper", axis="spec"),
        finding("P2", "judgement", "d.py", "Missing test", axis="spec"),
    ])
    write_jsonl(skills / "findings-correctness-100.jsonl", [
        finding("C1", "hard", "e.py", "Crash on empty input", axis="correctness"),
        finding("C2", "judgement", "f.py", "Stale docstring", axis="correctness"),
        finding("C3", "judgement", "f.py", "Overflow moved", axis="correctness"),
        finding("C4", "judgement", "f.py", "Second drift one", axis="correctness"),
        finding("C5", "judgement", "f.py", "Second drift two", axis="correctness"),
        finding("C6", "judgement", "f.py", "Second drift three", axis="correctness"),
        finding("C7", "judgement", "f.py", "Second drift four", axis="correctness"),
        finding("C8", "judgement", "f.py", "Second drift five", axis="correctness"),
    ])
    write_jsonl(skills / "dispositions-100.jsonl", [
        {"id": "S1", "outcome": "fixed", "sha": "aaa1111"},
        {"id": "S2", "outcome": "partial", "sha": "bbb2222"},
        {"id": "OE1", "outcome": "leftover", "file": "c.py", "title": "x",
         "severity": "judgement, PLAUSIBLE", "text": "kept"},
        {"id": "P1", "outcome": "fixed", "sha": "aaa1111"},
        {"id": "P2", "outcome": "not-fixed", "reason": "disputed: unreachable here"},
        {"id": "C1", "outcome": "fixed-with-regression", "sha": "ccc3333"},
        {"id": "C2", "outcome": "not_fixed", "text": "left for the sweep"},
        {"id": "C3", "outcome": "not-fixed", "reason": "rewrap moved the overflow rather than removing it"},
        {"id": "C4", "outcome": "regression"},
        {"id": "C5", "outcome": "contested"},
        {"id": "C6", "outcome": "open"},
        {"id": "C7", "outcome": "new"},
        {"id": "C8", "outcome": ["fixed"]},
        {"id": "codex-gate-1", "outcome": "leftover", "file": "z.py", "title": "t",
         "severity": "medium", "text": "codex leftover"},
    ])
    write_jsonl(skills / "findings-standards-101.jsonl", [
        finding("S1", "hard", "g.py", "No dispositions file for this one"),
    ])
    write_jsonl(skills / "findings-verify-102.jsonl", [
        finding("V1", "judgement", "h.py", "Hollow witness", axis="verify"),
    ])
    write_jsonl(skills / "dispositions-102.jsonl", [
        {"id": "V1", "outcome": "not-fixed"},
    ])
    write_jsonl(root / "agent-skills" / "findings-spec-103.jsonl", [
        finding("P1", "judgement", "i.py", "Wrong flag", axis="spec"),
    ])
    write_jsonl(root / "agent-skills" / "dispositions-103.jsonl", [
        {"id": "P1", "outcome": "fixed-partial", "sha": "ddd4444"},
    ])
    # 104: an OE finding whose file and title match a standards finding of its own run.
    write_jsonl(skills / "findings-standards-104.jsonl", [
        finding("S1", "judgement", "x.py", "Dead branch"),
        finding("OE1", "judgement", "x.py", "dead branch"),
    ])
    write_jsonl(skills / "dispositions-104.jsonl", [
        {"id": "S1", "outcome": "fixed", "sha": "e"}, {"id": "OE1", "outcome": "fixed", "sha": "e"}])
    # 105: same title, different files: not the same finding.
    write_jsonl(skills / "findings-standards-105.jsonl", [finding("S1", "judgement", "y.py", "Same title here")])
    write_jsonl(skills / "findings-spec-105.jsonl", [finding("P1", "judgement", "z.py", "Same title here", axis="spec")])
    write_jsonl(skills / "dispositions-105.jsonl", [
        {"id": "S1", "outcome": "fixed", "sha": "e"}, {"id": "P1", "outcome": "fixed", "sha": "e"}])
    # 106: a round-2 file, its ids round-prefixed, one of them an OE.
    write_jsonl(skills / "findings-standards-106-r2.jsonl", [
        finding("r2-S1", "judgement", "k.py", "Round two thing"),
        finding("r2-OE1", "judgement", "k.py", "Round two cut"),
    ])
    write_jsonl(skills / "dispositions-106.jsonl", [
        {"id": "r2-S1", "outcome": "fixed", "sha": "e"}, {"id": "r2-OE1", "outcome": "fixed", "sha": "e"}])
    # 107-108: a multi-ticket clump, dispositions named for the whole clump.
    write_jsonl(skills / "findings-spec-107-108.jsonl", [finding("P1", "hard", "m.py", "Clump finding", axis="spec")])
    write_jsonl(skills / "dispositions-107-108.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"}])
    # 109: off-pattern names, listed and not harvested.
    write_jsonl(skills / "findings-spec2-109.jsonl", [finding("P1", "hard", "n.py", "Misnamed", axis="spec")])
    write_jsonl(skills / "dispositions-109-v2.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"}])
    # 110: an empty sidecar. 111: one good line and one truncated line.
    (skills / "findings-correctness-110.jsonl").write_text("")
    (skills / "findings-spec-111.jsonl").write_text(
        json.dumps(finding("P1", "judgement", "q.py", "Half written", axis="spec")) + '\n{"id": "P2", "sev')
    write_jsonl(skills / "dispositions-111.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"}])
    # A scratch directory is not a review directory.
    write_jsonl(root / "scratch-9" / "findings-spec-999.jsonl", [
        finding("P1", "hard", "x.py", "scratch", axis="spec"),
    ])


def run(*args, home: Path):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, env=env)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def harvest(self, cache: Path):
        self.ledger = self.tmp / "ledger.jsonl"
        self.review = self.tmp / "review.md"
        result = run("harvest", "--cache", cache, "--ledger", self.ledger,
                     "--review-file", self.review, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def rows(self):
        return {r["row_id"]: r for r in map(json.loads, self.ledger.read_text().splitlines())}


class HarvestTest(Case):
    def setUp(self):
        super().setUp()
        self.cache = self.tmp / "cache"
        build_cache(self.cache)
        self.harvest(self.cache)

    def outcomes(self, row_id):
        return {f["id"]: (f["outcome"], f["severity"]) for f in self.rows()[row_id]["findings"]}

    def test_one_row_per_axis_run_plus_oe_split(self):
        self.assertEqual(sorted(self.rows()), [
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
        ])

    def test_oe_finding_leaves_the_standards_row(self):
        self.assertEqual(self.outcomes("skills/100/standards/1/findings-standards-100"),
                         {"S1": ("fixed", "hard"), "S2": ("fixed", "judgement")})
        self.assertEqual(self.outcomes("skills/100/over-engineering/1/findings-standards-100"),
                         {"OE1": ("leftover", "judgement")})

    def test_severity_joined_from_findings_not_from_dispositions(self):
        # OE1's disposition says "judgement, PLAUSIBLE"; the findings sidecar says judgement.
        self.assertEqual(self.outcomes("skills/100/spec/1/findings-spec-100")["P1"],
                         ("fixed", "hard"))
        self.assertEqual(self.outcomes("skills/100/over-engineering/1/findings-standards-100")["OE1"][1],
                         "judgement")

    def test_drifted_labels_map_to_canonical(self):
        self.assertEqual(self.outcomes("skills/100/spec/1/findings-spec-100")["P2"][0], "disputed")
        self.assertEqual(self.outcomes("skills/100/correctness/1/findings-correctness-100")["C2"][0],
                         "leftover")
        self.assertEqual(self.outcomes("skills/103/spec/1/findings-spec-103")["P1"][0], "fixed")
        s2 = next(f for f in self.rows()["skills/100/standards/1/findings-standards-100"]["findings"]
                  if f["id"] == "S2")
        self.assertTrue(s2["partial"])
        p1 = next(f for f in self.rows()["skills/100/spec/1/findings-spec-100"]["findings"]
                  if f["id"] == "P1")
        self.assertFalse(p1["partial"])

    def test_not_fixed_is_read_from_its_own_words(self):
        rows = self.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
        by_id = {f["id"]: f["outcome"] for f in rows}
        self.assertEqual(by_id["C3"], "leftover")  # a reason saying the fix did not land is not a dispute
        self.assertEqual(by_id["C2"], "leftover")

    def test_every_unmapped_or_malformed_outcome_is_unknown(self):
        rows = self.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
        by_id = {f["id"]: f["outcome"] for f in rows}
        for fid in ("C1", "C4", "C5", "C6", "C7", "C8"):
            self.assertEqual(by_id[fid], "unknown", fid)

    def test_round_comes_from_the_id_prefix_and_oe_keeps_its_round(self):
        rows = self.rows()
        self.assertEqual(rows["skills/106/standards/2/findings-standards-106-r2"]["round"], 2)
        oe = rows["skills/106/over-engineering/2/findings-standards-106-r2"]
        self.assertEqual([f["id"] for f in oe["findings"]], ["r2-OE1"])

    def test_multi_ticket_clump_rows_carry_every_ticket_and_join_their_dispositions(self):
        row = self.rows()["skills/107/spec/1/findings-spec-107-108"]
        self.assertEqual(row["tickets"], [107, 108])
        self.assertEqual(row["findings"][0]["outcome"], "fixed")

    def test_off_pattern_sidecars_are_listed_not_dropped(self):
        section = self.review.read_text().split("## Sidecars not harvested")[1].split("\n## ")[0]
        self.assertIn("findings-spec2-109.jsonl", section)
        self.assertIn("dispositions-109-v2.jsonl", section)
        self.assertFalse(any("/109/" in rid for rid in self.rows()))

    def test_empty_or_truncated_sidecar_is_unknown_findings_not_a_clean_review(self):
        empty = self.rows()["skills/110/correctness/1/findings-correctness-110"]
        self.assertEqual(empty["status"]["fields"]["findings"]["status"], "unknown")
        half = self.rows()["skills/111/spec/1/findings-spec-111"]
        self.assertEqual(half["status"]["fields"]["findings"]["status"], "unknown")
        self.assertEqual([f["id"] for f in half["findings"]], ["P1"])
        self.assertIn("findings-spec-111.jsonl: 1 unreadable line",
                      self.review.read_text().split("## Skipped lines")[1])
        clean = self.rows()["skills/100/spec/1/findings-spec-100"]
        self.assertEqual(clean["status"]["fields"]["findings"]["status"], "known")

    def test_verify_axis_becomes_verification(self):
        row = self.rows()["skills/102/verification/1/findings-verify-102"]
        self.assertEqual(row["type"], "verification")
        # not-fixed with neither a reason nor a text is not readable as leftover or disputed.
        self.assertEqual(row["findings"][0]["outcome"], "unknown")

    def test_alias_repo_folds_onto_skills(self):
        self.assertEqual(self.rows()["skills/103/spec/1/findings-spec-103"]["repo"], "skills")

    def test_unmapped_outcome_is_unknown_in_row_and_listed(self):
        c1 = next(f for f in self.rows()["skills/100/correctness/1/findings-correctness-100"]["findings"]
                  if f["id"] == "C1")
        self.assertEqual(c1["outcome"], "unknown")
        self.assertEqual(c1["outcome_status"]["status"], "unknown")
        self.assertIn("fixed-with-regression", c1["outcome_status"]["reason"])
        review = self.review.read_text()
        section = review.split("## Unmapped values")[1].split("\n## ")[0]
        self.assertIn("fixed-with-regression", section)

    def test_every_applied_mapping_is_listed(self):
        section = self.review.read_text().split("## Label mappings applied")[1].split("\n## ")[0]
        for label in ("partial", "fixed-partial", "not-fixed", "not_fixed", "verify"):
            self.assertIn(f"`{label}`", section)

    def test_missing_dispositions_file_is_unknown_not_leftover(self):
        row = self.rows()["skills/101/standards/1/findings-standards-101"]
        self.assertEqual(row["findings"][0]["outcome"], "unknown")
        self.assertIn("no dispositions file", row["findings"][0]["outcome_status"]["reason"])

    def test_shared_finding_marked_on_both_reviewers(self):
        s1 = next(f for f in self.rows()["skills/100/standards/1/findings-standards-100"]["findings"]
                  if f["id"] == "S1")
        p1 = next(f for f in self.rows()["skills/100/spec/1/findings-spec-100"]["findings"]
                  if f["id"] == "P1")
        self.assertEqual((s1["overlap"], s1["k"]), ("shared", 2))
        self.assertEqual((p1["overlap"], p1["k"]), ("shared", 2))
        p2 = next(f for f in self.rows()["skills/100/spec/1/findings-spec-100"]["findings"]
                  if f["id"] == "P2")
        self.assertEqual((p2["overlap"], p2["k"]), ("unique", 1))

    def test_oe_and_standards_are_one_reviewer(self):
        # OE1 and S2 share no file, but an OE match with its own standards report would not be overlap.
        rows = self.rows()
        for row_id in ("skills/104/standards/1/findings-standards-104",
                       "skills/104/over-engineering/1/findings-standards-104"):
            f = rows[row_id]["findings"][0]
            self.assertEqual((f["overlap"], f["k"]), ("unique", 1), row_id)
        section = self.review.read_text().split("## Overlap matches")[1].split("\n## ")[0]
        self.assertNotIn("Dead branch", section)  # a reviewer matching its own OE cut is not an overlap match

    def test_same_title_in_different_files_is_not_a_match(self):
        for row_id in ("skills/105/standards/1/findings-standards-105", "skills/105/spec/1/findings-spec-105"):
            f = self.rows()[row_id]["findings"][0]
            self.assertEqual((f["overlap"], f["k"]), ("unique", 1), row_id)

    def test_every_match_is_written_with_both_titles(self):
        section = self.review.read_text().split("## Overlap matches")[1].split("\n## ")[0]
        self.assertIn("Duplicated helper loader", section)
        self.assertIn("duplicated loader helper", section)
        self.assertNotIn("Long function", section)
        self.assertIn("Jaccard", section)

    def test_cost_fields_are_unknown_never_zero(self):
        for row in self.rows().values():
            for field in ("tokens", "wall_clock", "usage_delta"):
                self.assertEqual(row["cost"][field]["status"], "unknown")
                self.assertNotIn("value", row["cost"][field])

    def test_dispositions_with_no_finding_are_listed_not_dropped(self):
        section = self.review.read_text().split("## Dispositions with no finding")[1].split("\n## ")[0]
        self.assertIn("codex-gate-1", section)

    def test_scratch_directories_are_skipped(self):
        self.assertFalse(any("999" in rid for rid in self.rows()))

    def test_no_mutation_rows(self):
        self.assertFalse(any("mutation" in r["type"] for r in self.rows().values()))


class HarvestRerunTest(Case):
    def test_same_tree_twice_gives_identical_ledger(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        self.harvest(cache)
        first = self.ledger.read_text()
        self.harvest(cache)
        self.assertEqual(self.ledger.read_text(), first)
        self.assertEqual(len(first.splitlines()), 16)

    def test_a_row_no_longer_in_the_cache_leaves_the_ledger(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        self.harvest(cache)
        (cache / "skills" / "findings-standards-101.jsonl").rename(cache / "skills" / "notes-101.txt")
        self.harvest(cache)
        self.assertEqual(len(self.ledger.read_text().splitlines()), 15)
        self.assertNotIn("skills/101/standards/1/findings-standards-101", self.ledger.read_text())

    def test_rows_not_written_by_harvest_survive_a_reharvest(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        self.harvest(cache)
        other = {"row_id": "skills/9/codex-gate/1/x", "origin": "append", "type": "codex-gate", "findings": []}
        with self.ledger.open("a") as fh:
            fh.write(json.dumps(other) + "\n")
        self.harvest(cache)
        self.assertIn("skills/9/codex-gate/1/x", self.ledger.read_text())

    def test_cache_with_no_sidecars_fails_loud(self):
        cache = self.tmp / "cache"
        (cache / "skills").mkdir(parents=True)
        result = run("harvest", "--cache", cache, "--ledger", self.tmp / "l.jsonl",
                     "--review-file", self.tmp / "r.md", home=self.home)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no findings or dispositions sidecars", result.stderr)

    def test_corrupt_existing_ledger_fails_loud_and_is_left_alone(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        ledger = self.tmp / "l.jsonl"
        ledger.write_text("{not json\n")
        result = run("harvest", "--cache", cache, "--ledger", ledger,
                     "--review-file", self.tmp / "r.md", home=self.home)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(ledger.read_text(), "{not json\n")

    def test_default_cache_is_under_home_never_the_real_one(self):
        result = run("harvest", "--ledger", self.tmp / "l.jsonl",
                     "--review-file", self.tmp / "r.md", home=self.home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.home), result.stderr)


def report_rows():
    def f(fid, sev, outcome, overlap="unique", k=1):
        return {"id": fid, "severity": sev, "outcome": outcome, "partial": False,
                "overlap": overlap, "k": k}

    def row(rid, typ, findings, findings_status="known"):
        return {"row_id": rid, "repo": "skills", "ticket": 1, "type": typ, "round": 1,
                "findings": findings,
                "status": {"fields": {"findings": {"status": findings_status}}},
                "cost": {"tokens": {"status": "unknown", "reason": "n/a"}}}

    return [
        row("r1", "standards", [
            f("a", "hard", "fixed"),
            f("b", "judgement", "filed", "shared", 2),
            f("c", "hard", "leftover"),
            f("d", "judgement", "disputed"),
            f("e", "judgement", "unknown"),
        ], "unknown"),
        row("r2", "spec", [
            f("f", "hard", "fixed", "shared", 2),
            f("g", "weird", "fixed"),
        ]),
    ]


class ReportTest(Case):
    def report(self, *extra, rows=None):
        ledger = self.tmp / "in.jsonl"
        write_jsonl(ledger, rows or report_rows())
        result = run("report", "--ledger", ledger, "--format", "json", *extra, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {t["type"]: t for t in json.loads(result.stdout)["types"]}

    def test_table_matches_hand_computed_values(self):
        types = self.report()
        self.assertEqual(types["standards"], {
            "type": "standards", "rows": 1, "findings": 5, "value": 3.5,
            "unique_share": 0.8, "leftover_rate": 0.25, "dispute_rate": 0.25,
            "unknown_outcomes": 1, "unweighted": 0, "unknown_finding_rows": 1,
            "unknown_cost_rows": 1})
        self.assertEqual(types["spec"], {
            "type": "spec", "rows": 1, "findings": 2, "value": 1.5,
            "unique_share": 0.5, "leftover_rate": 0.0, "dispute_rate": 0.0,
            "unknown_outcomes": 0, "unweighted": 1, "unknown_finding_rows": 0,
            "unknown_cost_rows": 1})

    def test_severity_weights_are_a_parameter(self):
        weights = self.tmp / "w.json"
        weights.write_text(json.dumps({"hard": 10, "judgement": 2}))
        types = self.report("--weights", weights)
        # a hard fixed 10 + b judgement filed shared 2/2
        self.assertEqual(types["standards"]["value"], 11.0)
        self.assertEqual(types["spec"]["value"], 5.0)

    def test_overlap_split_divides_a_shared_finding_by_k(self):
        types = self.report()
        self.assertEqual(types["spec"]["value"], 1.5)  # hard 3 / k=2
        types = self.report("--split", "none")
        self.assertEqual(types["spec"]["value"], 3.0)

    def test_leftover_carries_no_value(self):
        only_leftover = [dict(report_rows()[0], findings=[
            {"id": "c", "severity": "hard", "outcome": "leftover", "partial": False,
             "overlap": "unique", "k": 1}])]
        types = self.report(rows=only_leftover)
        self.assertEqual(types["standards"]["value"], 0.0)
        self.assertEqual(types["standards"]["leftover_rate"], 1.0)

    def test_disputed_carries_no_value(self):
        only_disputed = [dict(report_rows()[0], findings=[
            {"id": "d", "severity": "hard", "outcome": "disputed", "partial": False,
             "overlap": "unique", "k": 1}])]
        types = self.report(rows=only_disputed)
        self.assertEqual(types["standards"]["value"], 0.0)
        self.assertEqual(types["standards"]["dispute_rate"], 1.0)

    def test_markdown_table_and_mutation_note(self):
        ledger = self.tmp / "in.jsonl"
        write_jsonl(ledger, report_rows())
        result = run("report", "--ledger", ledger, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("| standards | 1 | 5 | 3.50 | 80.0% | 25.0% | 25.0% | 1 | 0 | 1 | 1 |", lines)
        self.assertIn("No mutation rows", result.stdout)

    def test_a_type_outside_the_known_list_is_still_reported(self):
        odd = dict(report_rows()[0], row_id="r9", type="future-review")
        self.assertIn("future-review", self.report(rows=[odd]))

    def test_mutation_note_only_when_no_mutation_rows(self):
        ledger = self.tmp / "in.jsonl"
        mut = dict(report_rows()[0], row_id="r8", type="worker-mutation")
        write_jsonl(ledger, [mut])
        result = run("report", "--ledger", ledger, home=self.home)
        self.assertNotIn("No mutation rows", result.stdout)

    def test_missing_ledger_fails_loud(self):
        result = run("report", "--ledger", self.tmp / "absent.jsonl", home=self.home)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
