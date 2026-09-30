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
    # 112: a plainly named file whose every id is round 2 holds no round-1 run.
    write_jsonl(skills / "findings-spec-112.jsonl", [finding("r2-P1", "judgement", "w.py", "Later round", axis="spec")])
    write_jsonl(skills / "dispositions-112.jsonl", [{"id": "r2-P1", "outcome": "fixed", "sha": "e"}])
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
            "skills/112/spec/2/findings-spec-112",
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

    def test_without_transcripts_cost_is_unknown_never_zero_and_oe_is_inside_standards(self):
        for row in self.rows().values():
            for field in ("tokens", "wall_clock"):
                want = "inside-standards" if row["type"] == "over-engineering" else "unknown"
                self.assertEqual(row["cost"][field]["status"], want)
                self.assertNotIn("value", row["cost"][field])
            self.assertEqual(row["cost"]["usage_delta"]["status"], "not-applicable")

    def test_dispositions_with_no_finding_are_listed_not_dropped(self):
        section = self.review.read_text().split("## Dispositions with no finding")[1].split("\n## ")[0]
        self.assertIn("codex-gate-1", section)

    def test_scratch_directories_are_skipped(self):
        self.assertFalse(any("999" in rid for rid in self.rows()))

    def test_no_mutation_rows(self):
        self.assertFalse(any("mutation" in r["type"] for r in self.rows().values()))


class VerificationOverlapTest(Case):
    """Ruling 8 (P6 on PR #1275): the verification pass never counts toward
    overlap for a round-1 finding it re-checks."""
    def setUp(self):
        super().setUp()
        cache = self.tmp / "cache"
        skills = cache / "skills"
        write_jsonl(skills / "findings-standards-200.jsonl", [finding("S1", "hard", "a.py", "Widget leak on close")])
        write_jsonl(skills / "findings-verify-200.jsonl", [
            finding("V1", "judgement", "a.py", "widget leak on close", axis="verify"),
            finding("V2", "judgement", "b.py", "Fix left a stale docstring", axis="verify")])
        write_jsonl(skills / "dispositions-200.jsonl", [
            {"id": "S1", "outcome": "fixed", "sha": "e"}, {"id": "V1", "outcome": "fixed", "sha": "e"},
            {"id": "V2", "outcome": "fixed", "sha": "e"}])
        self.harvest(cache)

    def find(self, kind, fid):
        row = next(r for r in self.rows().values() if r["type"] == kind)
        return next(f for f in row["findings"] if f["id"] == fid)

    def test_restated_round_one_finding_stays_unique(self):
        f = self.find("standards", "S1")
        self.assertEqual((f["overlap"], f["k"]), ("unique", 1))

    def test_the_restating_verification_finding_earns_no_credit(self):
        f = self.find("verification", "V1")
        self.assertEqual((f["overlap"], f["k"]), ("restated", 1))
        ledger = self.tmp / "ledger.jsonl"
        out = json.loads(run("report", "--ledger", ledger, "--format", "json", home=self.home).stdout)
        verification = next(t for t in out["types"] if t["type"] == "verification")
        # V1 restates S1 (fixed, judgement 1, would be worth 1); only V2 counts.
        self.assertEqual(verification["value"], 1.0)
        standards = next(t for t in out["types"] if t["type"] == "standards")
        self.assertEqual(standards["value"], 3.0)  # S1 hard, unique, undivided

    def test_finding_the_verification_pass_raises_new_keeps_its_credit(self):
        f = self.find("verification", "V2")
        self.assertEqual((f["overlap"], f["k"]), ("unique", 1))

    def test_restatement_is_listed_apart_from_overlap_matches(self):
        text = self.review.read_text()
        self.assertNotIn("Widget leak", text.split("## Overlap matches")[1].split("\n## ")[0])
        self.assertIn("Widget leak", text.split("## Verification restatements")[1].split("\n## ")[0])


def usage(inp, out, cw, cr):
    return {"input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def transcript(root: Path, project: str, agent: str, description: str, first: str, lines: list,
               agent_type="diff-reviewer", session="s1"):
    """One subagent transcript. `lines` are (timestamp, message id, usage or None) triples;
    a repeated message id is one streamed message written as several lines."""
    d = root / project / session / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"agent-{agent}.meta.json").write_text(json.dumps(
        {"agentType": agent_type, "description": description, "model": "opus"}))
    out = [{"type": "user", "timestamp": lines[0][0], "message": {"role": "user", "content": first}}]
    for ts, mid, u in lines:
        msg = {"role": "assistant", "id": mid, "model": "claude-opus-5-5", "content": []}
        if u is not None:
            msg["usage"] = u
        out.append({"type": "assistant", "timestamp": ts, "message": msg})
    (d / f"agent-{agent}.jsonl").write_text("".join(json.dumps(o) + "\n" for o in out))


def wt(repo_path: str, n: int) -> str:
    """The project directory Claude Code names for a worktree."""
    return f"{repo_path}--claude-worktrees-implement-{n}"


SKILLS_PROJ = "-home-u--agents-skills"
OTHER_PROJ = "-home-u-src-otherrepo"


def build_cost_fixture(root: Path) -> tuple[Path, Path]:
    cache, tr = root / "cache", root / "projects"
    skills, other = cache / "skills", cache / "otherrepo"
    for n in (401, 402):
        write_jsonl(skills / f"findings-standards-{n}.jsonl", [finding("S1", "hard", "a.py", f"Thing {n}")])
        write_jsonl(skills / f"dispositions-{n}.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"}])
    write_jsonl(skills / "findings-spec-405.jsonl", [finding("P1", "hard", "a.py", "Thing 405", axis="spec")])
    write_jsonl(skills / "dispositions-405.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"}])
    write_jsonl(skills / "findings-standards-400.jsonl", [
        finding("S1", "hard", "a.py", "Thing 400"), finding("OE1", "judgement", "c.py", "Wrapper")])
    write_jsonl(skills / "findings-spec-400.jsonl", [finding("P1", "judgement", "d.py", "Spec thing", axis="spec")])
    write_jsonl(skills / "findings-correctness-400.jsonl", [
        finding("C1", "judgement", "e.py", "Corr thing", axis="correctness")])
    write_jsonl(skills / "dispositions-400.jsonl", [
        {"id": i, "outcome": "fixed", "sha": "e"} for i in ("S1", "OE1", "P1", "C1")])
    write_jsonl(skills / "findings-verify-403.jsonl", [finding("V1", "judgement", "v.py", "Hollow", axis="verify")])
    write_jsonl(skills / "dispositions-403.jsonl", [{"id": "V1", "outcome": "fixed", "sha": "e"}])
    write_jsonl(skills / "findings-standards-404-r2.jsonl", [finding("r2-S1", "hard", "r.py", "Round two")])
    write_jsonl(skills / "dispositions-404.jsonl", [{"id": "r2-S1", "outcome": "fixed", "sha": "e"}])
    write_jsonl(other / "findings-standards-400.jsonl", [finding("S1", "hard", "o.py", "Other repo")])
    write_jsonl(other / "dispositions-400.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"}])
    p400 = wt(SKILLS_PROJ, 400)
    # Standards: one streamed message (two lines, the second final) and one more; 330 s.
    transcript(tr, p400, "std", "Standards axis review of #400 diff", "Axis: **Standards**. Repo: x", [
        ("2026-09-20T10:00:00.000Z", "m1", usage(2, 1, 100, 10)),
        ("2026-09-20T10:00:05.000Z", "m1", usage(2, 50, 100, 10)),
        ("2026-09-20T10:05:30.000Z", "m2", usage(3, 70, 20, 200))])
    transcript(tr, p400, "spec", "Spec review #400", "Repo: x", [
        ("2026-09-20T10:00:00.000Z", "m1", usage(10, 20, 30, 40)),
        ("2026-09-20T10:01:00.000Z", "m2", usage(0, 0, 0, 0))])
    # A generic description: the axis comes from the first message.
    transcript(tr, p400, "cor", "Reviewer", "Axis: correctness. Repo: x", [
        ("2026-09-20T10:00:00.000Z", "m1", usage(1, 2, 3, 4))])
    transcript(tr, wt(OTHER_PROJ, 400), "oth", "Standards review #400", "Repo: y", [
        ("2026-09-21T09:00:00.000Z", "m1", usage(7, 7, 7, 7))])
    transcript(tr, wt(SKILLS_PROJ, 402), "nou", "Standards review #402", "Repo: x", [
        ("2026-09-20T11:00:00.000Z", "m1", None), ("2026-09-20T11:02:00.000Z", "m2", None)])
    transcript(tr, wt(SKILLS_PROJ, 403), "ver", "Verification pass", "Verification of round 1", [
        ("2026-09-20T12:00:00.000Z", "m1", usage(5, 5, 5, 5))])
    transcript(tr, wt(SKILLS_PROJ, 404), "rnd", "Standards review round-2 #404", "Repo: x", [
        ("2026-09-20T13:00:00.000Z", "m1", usage(6, 6, 6, 6))])
    transcript(tr, wt(SKILLS_PROJ, 405), "sp1", "Spec review #405", "Repo: x", [
        ("2026-09-20T14:00:00.000Z", "m1", usage(1, 1, 1, 1))])
    transcript(tr, wt(SKILLS_PROJ, 405), "sp2", "Spec review #405 retry", "Repo: x", [
        ("2026-09-20T14:10:00.000Z", "m1", usage(2, 2, 2, 2))], session="s2")
    # A verification pass whose findings sidecar was never written: still a run.
    transcript(tr, wt(SKILLS_PROJ, 406), "vno", "Verify dispositions #406", "Repo: x", [
        ("2026-09-20T15:00:00.000Z", "m1", usage(9, 9, 9, 9))])
    # Not attributable: no ticket anywhere.
    transcript(tr, SKILLS_PROJ, "lost", "Standards review", "Repo: x", [
        ("2026-09-20T16:00:00.000Z", "m1", usage(99, 99, 99, 99))])
    # Not a diff-reviewer: ignored.
    transcript(tr, p400, "gp", "Standards review #400", "Repo: x", [
        ("2026-09-20T16:00:00.000Z", "m1", usage(500, 500, 500, 500))], agent_type="general-purpose")
    (tr / p400 / "s1" / "subagents" / "agent-bad.meta.json").write_text("")
    add_edge_cases(cache, tr)
    return cache, tr


def add_edge_cases(cache: Path, tr: Path) -> None:
    """Transcripts the real tree holds that a plain fixture would not: a stated round, a torn or
    malformed transcript, a spec-level review run from a ticket worktree, two sidecar rows for one
    key, a repo spelled differently in the cache and the project directory, a worktree that is not
    `implement-N`, a verification pass whose round differs from its sidecar's, a conflicting axis."""
    skills = cache / "skills"

    def sidecar(repo_dir: Path, axis: str, n: int, name=None, fid="S1", prefix=""):
        write_jsonl(repo_dir / (name or f"findings-{axis}-{n}.jsonl"),
                    [finding(f"{prefix}{fid}", "hard", "a.py", f"Thing {n}", axis=axis)])
        write_jsonl(repo_dir / f"dispositions-{n}.jsonl", [{"id": f"{prefix}{fid}", "outcome": "fixed", "sha": "e"}])

    def one(project, agent, desc, first, ts, u):
        transcript(tr, project, agent, desc, first, [(t, f"m{i}", u) for i, (t, u) in enumerate(zip(ts, u))])

    ok = usage(4, 4, 4, 4)
    sidecar(skills, "standards", 407, "findings-standards-407-r2.jsonl", prefix="r2-")
    one(wt(SKILLS_PROJ, 407), "prf", "Standards review #407", "Axis: standards. id prefix: r2-",
        ["2026-09-20T10:00:00Z"], [ok])
    sidecar(skills, "standards", 408)
    one(wt(SKILLS_PROJ, 408), "bad", "Standards review #408", "Repo: x",
        ["2026-09-20T10:00:00Z", "2026-09-20T10:01:00Z"], [ok, {"input_tokens": 1, "output_tokens": None}])
    sidecar(skills, "standards", 409)
    one(wt(SKILLS_PROJ, 409), "torn", "Standards review #409", "Repo: x", ["2026-09-20T10:00:00Z"], [ok])
    with open(tr / wt(SKILLS_PROJ, 409) / "s1" / "subagents" / "agent-torn.jsonl", "a") as f:
        f.write('{"type": "assistant", "timest')
    sidecar(skills, "standards", 410)
    one(wt(SKILLS_PROJ, 410), "tz", "Standards review #410", "Repo: x",
        ["2026-09-20T10:00:00", "2026-09-20T10:01:00Z"], [ok, ok])
    sidecar(skills, "spec", 411, fid="P1")
    one(wt(SKILLS_PROJ, 411), "lvl", "Spec axis spec-9 review",
        "Axis: **Spec**. Worktree under review: /x/.claude/worktrees/review-spec-9 (detached)",
        ["2026-09-20T10:00:00Z"], [usage(77, 77, 77, 77)])
    sidecar(skills, "correctness", 412, fid="C1")
    write_jsonl(skills / "findings-correctness-412-round1.jsonl", [finding("C1", "hard", "a.py", "Thing 412", axis="correctness")])
    one(wt(SKILLS_PROJ, 412), "twin", "Correctness review #412", "Repo: x", ["2026-09-20T10:00:00Z"], [ok])
    write_jsonl(cache / "foo_bar" / "findings-standards-413.jsonl", [finding("S1", "hard", "a.py", "Thing 413")])
    write_jsonl(cache / "foo_bar" / "dispositions-413.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"}])
    one(wt("-home-u-src-foo-bar", 413), "und", "Standards review #413", "Repo: x", ["2026-09-20T10:00:00Z"], [ok])
    write_jsonl(cache / "otherrepo" / "findings-standards-414.jsonl", [finding("S1", "hard", "a.py", "Thing 414")])
    write_jsonl(cache / "otherrepo" / "dispositions-414.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "e"}])
    one(OTHER_PROJ + "--claude-worktrees-drills-qqrr", "drl", "Standards review #414", "Repo: x",
        ["2026-09-20T10:00:00Z"], [ok])
    sidecar(skills, "verify", 415, "findings-verify-415.jsonl", fid="V1")
    one(wt(SKILLS_PROJ, 415), "vr2", "Verification pass round-2 #415", "Repo: x", ["2026-09-20T10:00:00Z"], [ok])
    sidecar(skills, "standards", 416)
    one(wt(SKILLS_PROJ, 416), "cfl", "Standards review #416", "Axis: spec. Repo: x", ["2026-09-20T10:00:00Z"],
        [usage(66, 66, 66, 66)])
    sidecar(skills, "standards", 418)
    one(wt(SKILLS_PROJ, 418), "bts", "Standards review #418", "Repo: x",
        ["2026-09-20T10:00:00Z", "yesterday"], [ok, ok])
    sidecar(skills, "standards", 417)
    d = tr / wt(SKILLS_PROJ, 417) / "s1" / "subagents"
    d.mkdir(parents=True)
    (d / "agent-dir.meta.json").write_text(json.dumps({"agentType": "diff-reviewer", "description": "Standards review #417"}))
    (d / "agent-dir.jsonl").mkdir()


class CostHarvestTest(Case):
    def setUp(self):
        super().setUp()
        self.cache, self.tr = build_cost_fixture(self.tmp)
        self.ledger = self.tmp / "ledger.jsonl"
        self.review = self.tmp / "review.md"
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
                "--review-file", self.review, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    def cost(self, row_id):
        return self.rows()[row_id]["cost"]

    def test_tokens_by_kind_from_the_axis_transcript_deduping_streamed_lines(self):
        t = self.cost("skills/400/standards/1/findings-standards-400")["tokens"]
        self.assertEqual(t, {"status": "known", "input": 5, "output": 120, "cache_write": 120, "cache_read": 210})

    def test_two_reviewers_of_one_pr_each_get_their_own_transcript(self):
        spec = self.cost("skills/400/spec/1/findings-spec-400")["tokens"]
        corr = self.cost("skills/400/correctness/1/findings-correctness-400")["tokens"]
        self.assertEqual((spec["input"], spec["output"], spec["cache_write"], spec["cache_read"]), (10, 20, 30, 40))
        self.assertEqual((corr["input"], corr["output"], corr["cache_write"], corr["cache_read"]), (1, 2, 3, 4))

    def test_the_same_ticket_number_in_another_repo_is_not_mixed_in(self):
        other = self.cost("otherrepo/400/standards/1/findings-standards-400")["tokens"]
        self.assertEqual(other["input"], 7)
        self.assertEqual(self.cost("skills/400/standards/1/findings-standards-400")["tokens"]["input"], 5)

    def test_wall_clock_is_first_to_last_timestamp(self):
        w = self.cost("skills/400/standards/1/findings-standards-400")["wall_clock"]
        self.assertEqual((w["status"], w["seconds"]), ("known", 330))
        self.assertEqual((w["start"], w["end"]), ("2026-09-20T10:00:00.000Z", "2026-09-20T10:05:30.000Z"))

    def test_row_model_is_read_from_the_transcript(self):
        self.assertEqual(self.rows()["skills/400/spec/1/findings-spec-400"]["model"], "claude-opus-5-5")

    def test_round_two_transcript_attributes_to_the_round_two_row(self):
        self.assertEqual(self.cost("skills/404/standards/2/findings-standards-404-r2")["tokens"]["input"], 6)

    def test_verification_transcript_attributes_to_the_verify_sidecar_row(self):
        self.assertEqual(self.cost("skills/403/verification/1/findings-verify-403")["tokens"]["input"], 5)

    def test_transcript_without_usage_is_unknown_tokens_never_zero(self):
        c = self.cost("skills/402/standards/1/findings-standards-402")
        self.assertEqual(c["tokens"]["status"], "unknown")
        self.assertIn("usage", c["tokens"]["reason"])
        for kind in ("input", "output", "cache_write", "cache_read"):
            self.assertNotIn(kind, c["tokens"])
        self.assertEqual(c["wall_clock"]["seconds"], 120)

    def test_axis_run_with_no_transcript_is_unknown_never_zero(self):
        c = self.cost("skills/401/standards/1/findings-standards-401")
        for field in ("tokens", "wall_clock"):
            self.assertEqual(c[field]["status"], "unknown", field)
            self.assertIn("no transcript", c[field]["reason"])
            self.assertNotIn("input", c[field])
            self.assertNotIn("seconds", c[field])

    def test_two_transcripts_for_one_row_are_summed_and_both_listed(self):
        row = self.rows()["skills/405/spec/1/findings-spec-405"]
        self.assertEqual(row["cost"]["tokens"]["input"], 3)
        self.assertEqual(len([s for s in row["status"]["sources"] if "agent-" in s]), 2)

    def test_over_engineering_cost_stays_inside_standards(self):
        oe = self.cost("skills/400/over-engineering/1/findings-standards-400")
        self.assertEqual(oe["tokens"]["status"], "inside-standards")
        self.assertEqual(oe["wall_clock"]["status"], "inside-standards")
        self.assertNotIn("input", oe["tokens"])

    def test_verification_run_without_a_sidecar_gets_its_own_row(self):
        row = next(r for rid, r in self.rows().items() if r["type"] == "verification" and r["ticket"] == 406)
        self.assertEqual(row["cost"]["tokens"]["input"], 9)
        self.assertEqual(row["findings"], [])
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "unknown")

    def test_unattributable_transcripts_are_listed_with_a_reason_not_dropped(self):
        section = self.review.read_text().split("## Transcripts not attributed")[1].split("\n## ")[0]
        self.assertIn("agent-lost", section)
        self.assertIn("no ticket", section)
        self.assertIn("agent-bad", section)
        self.assertNotIn("agent-gp", section)  # a non diff-reviewer is out of scope, not a failure

    def test_unattributed_spend_is_in_no_row(self):
        seen = [r["cost"]["tokens"].get("input") for r in self.rows().values()]
        for unattributed in (99, 500, 77, 66):
            self.assertNotIn(unattributed, seen)

    def tokens_of(self, row_id):
        return self.cost(row_id)["tokens"]

    def unattributed_section(self):
        return self.review.read_text().split("## Transcripts not attributed")[1].split("\n## ")[0]

    def test_round_is_read_from_the_id_prefix_the_brief_names(self):
        self.assertEqual(self.tokens_of("skills/407/standards/2/findings-standards-407-r2")["input"], 4)

    def test_a_message_with_a_malformed_usage_block_makes_tokens_unknown(self):
        t = self.tokens_of("skills/408/standards/1/findings-standards-408")
        self.assertEqual(t["status"], "unknown")
        self.assertIn("usage", t["reason"])

    def test_a_torn_transcript_makes_tokens_unknown(self):
        t = self.tokens_of("skills/409/standards/1/findings-standards-409")
        self.assertEqual(t["status"], "unknown")
        self.assertIn("unreadable", t["reason"])

    def test_a_torn_transcript_or_an_unparseable_timestamp_makes_wall_clock_unknown(self):
        torn = self.cost("skills/409/standards/1/findings-standards-409")["wall_clock"]
        self.assertEqual(torn["status"], "unknown")
        self.assertIn("unreadable", torn["reason"])
        bad = self.cost("skills/418/standards/1/findings-standards-418")["wall_clock"]
        self.assertEqual(bad["status"], "unknown")
        self.assertIn("timestamp", bad["reason"])

    def test_naive_and_aware_timestamps_do_not_crash_the_harvest(self):
        self.assertEqual(self.cost("skills/410/standards/1/findings-standards-410")["wall_clock"]["seconds"], 60)

    def test_a_review_of_a_review_worktree_is_not_charged_to_the_ticket_worktree_it_ran_in(self):
        row = self.cost("skills/411/spec/1/findings-spec-411")
        self.assertEqual(row["tokens"]["status"], "unknown")
        self.assertIn("agent-lvl", self.unattributed_section())
        self.assertIn("spec-level", self.unattributed_section())

    def test_two_sidecar_rows_for_one_key_both_say_so_rather_than_one_taking_the_cost(self):
        for rid in ("skills/412/correctness/1/findings-correctness-412",
                    "skills/412/correctness/1/findings-correctness-412-round1"):
            t = self.tokens_of(rid)
            self.assertEqual(t["status"], "unknown", rid)
            self.assertIn("share", t["reason"])
        self.assertFalse([r for r in self.rows() if r.startswith("skills/412/") and r.endswith("/agent-twin")])

    def test_a_repo_spelled_with_an_underscore_matches_its_project_directory(self):
        self.assertEqual(self.tokens_of("foo_bar/413/standards/1/findings-standards-413")["input"], 4)
        self.assertFalse([r for r in self.rows() if r.startswith("foo-bar/")])

    def test_a_worktree_not_named_implement_n_is_listed_because_its_repo_cannot_be_told(self):
        # .../src/drills/.claude/worktrees/<name> may be a checkout of a different repo than "drills".
        self.assertEqual(self.tokens_of("otherrepo/414/standards/1/findings-standards-414")["status"], "unknown")
        self.assertIn("agent-drl", self.unattributed_section())
        self.assertIn("not implement-N", self.unattributed_section())
        self.assertFalse([r for r in self.rows() if r.startswith("otherrepo--") or "drills" in r])

    def test_a_verification_run_joins_the_only_verify_row_when_its_round_differs(self):
        self.assertEqual(self.tokens_of("skills/415/verification/1/findings-verify-415")["input"], 4)

    def test_description_and_first_message_naming_different_axes_is_listed_not_guessed(self):
        self.assertEqual(self.tokens_of("skills/416/standards/1/findings-standards-416")["status"], "unknown")
        self.assertIn("agent-cfl", self.unattributed_section())

    def test_transcripts_behind_a_shared_key_are_listed(self):
        section = self.review.read_text().split("## Transcripts behind a key several sidecar rows share")[1].split("\n## ")[0]
        self.assertIn("agent-twin", section)

    def test_an_unreadable_transcript_is_listed_and_does_not_stop_the_harvest(self):
        self.assertIn("agent-dir", self.unattributed_section())

    def test_rows_that_sum_several_transcripts_are_listed(self):
        section = self.review.read_text().split("## Rows with more than one transcript")[1].split("\n## ")[0]
        self.assertIn("findings-spec-405", section)

    def test_reharvest_gives_the_same_ledger(self):
        first = self.ledger.read_text()
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tr, "--ledger", self.ledger,
                "--review-file", self.review, home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.ledger.read_text(), first)

    def test_missing_explicit_transcripts_tree_fails_loud(self):
        r = run("harvest", "--cache", self.cache, "--transcripts", self.tmp / "nope", "--ledger",
                self.tmp / "l2.jsonl", "--review-file", self.tmp / "r2.md", home=self.home)
        self.assertEqual(r.returncode, 2)

    def test_default_transcripts_tree_missing_is_unknown_cost_not_a_failure(self):
        r = run("harvest", "--cache", self.cache, "--ledger", self.tmp / "l3.jsonl",
                "--review-file", self.tmp / "r3.md", home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = [json.loads(x) for x in (self.tmp / "l3.jsonl").read_text().splitlines()]
        self.assertTrue(all(r["cost"]["tokens"]["status"] in ("unknown", "inside-standards") for r in rows))
        self.assertIn("not found", rows[0]["cost"]["tokens"].get("reason", "not found"))


class HarvestRerunTest(Case):
    def test_same_tree_twice_gives_identical_ledger(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        self.harvest(cache)
        first = self.ledger.read_text()
        self.harvest(cache)
        self.assertEqual(self.ledger.read_text(), first)
        self.assertEqual(len(first.splitlines()), 17)

    def test_a_row_no_longer_in_the_cache_leaves_the_ledger(self):
        cache = self.tmp / "cache"
        build_cache(cache)
        self.harvest(cache)
        (cache / "skills" / "findings-standards-101.jsonl").rename(cache / "skills" / "notes-101.txt")
        self.harvest(cache)
        self.assertEqual(len(self.ledger.read_text().splitlines()), 16)
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


def cost_rows():
    """Rows with cost, computed by hand in CostReportTest. Prices are per million tokens."""
    def fnd(fid, sev, outcome="fixed", overlap="unique", k=1):
        return {"id": fid, "severity": sev, "outcome": outcome, "partial": False, "overlap": overlap, "k": k}

    def row(rid, typ, model, tokens, secs, findings, findings_status="known", ticket=1):
        tk = {"status": "known", **tokens} if isinstance(tokens, dict) else tokens
        wall = {"status": "known", "seconds": secs} if secs is not None else {"status": "unknown", "reason": "x"}
        return {"row_id": rid, "repo": "skills", "ticket": ticket, "type": typ, "round": 1, "model": model,
                "findings": findings, "status": {"fields": {"findings": {"status": findings_status}}},
                "cost": {"tokens": tk, "wall_clock": wall}}

    def tok(i=0, o=0, cw=0, cr=0):
        return {"input": i, "output": o, "cache_write": cw, "cache_read": cr}

    inside = {"status": "inside-standards", "reason": "in standards"}
    return [
        row("A", "standards", "m-opus", tok(1_000_000, 100_000, 200_000, 3_000_000), 100, [fnd("a", "hard")]),
        row("B", "standards", "m-opus", tok(2_000_000), 50, [fnd("b", "judgement")], ticket=2),
        row("C", "standards", "m-opus", {"status": "unknown", "reason": "transcript has no usage block"}, None,
            [fnd("c", "hard")], ticket=3),
        row("D", "standards", "m-unpriced", tok(10), 5, [fnd("d", "hard")], ticket=4),
        row("E", "over-engineering", None, inside, None, [fnd("e", "judgement")]),  # A's ticket
        row("E3", "over-engineering", None, inside, None, [fnd("e3", "hard")], ticket=3),  # C's: cost unknown
        row("E4", "over-engineering", None, inside, None, [fnd("e4", "hard")], ticket=4),  # D's: unpriced
        dict(row("E2", "over-engineering", None, inside, None, []),
             cost={"tokens": inside, "wall_clock": inside}),
        row("F", "spec", "m-sonnet", tok(1_000_000, 1_000_000), 60, [fnd("f", "hard", "fixed", "shared", 2)]),
        row("G", "spec", "m-sonnet", {"status": "unknown", "reason": "no transcript"}, None, [], "unknown"),
        # H: a priced run whose sidecar was never written; its $3 must stay out of value per dollar.
        row("H", "spec", "m-sonnet", tok(1_000_000), 10, [], "unknown"),
    ]


PRICES = {"m-opus": {"input": 15, "output": 75, "cache_write": 18.75, "cache_read": 1.5},
          "m-sonnet": {"input": 3, "output": 15, "cache_write": 3.75, "cache_read": 0.3}}


class CostReportTest(Case):
    def report(self, prices=PRICES, *extra, fmt="json"):
        ledger = self.tmp / "in.jsonl"
        write_jsonl(ledger, cost_rows())
        args = ["report", "--ledger", ledger, "--format", fmt, *extra]
        if prices is not None:
            pf = self.tmp / "prices.json"
            pf.write_text(json.dumps(prices))
            args += ["--prices", pf]
        result = run(*args, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        if fmt != "json":
            return result.stdout
        out = json.loads(result.stdout)
        self.notes = out["notes"]
        return {t["type"]: t for t in out["types"]}

    def test_dollars_match_the_hand_computed_fixture(self):
        # A: 15 + 7.5 + 3.75 + 4.5 = 30.75.  B: 2 x 15 = 30.  D has no price, C no tokens.
        std = self.report()["standards"]
        self.assertEqual(std["dollars"], 60.75)
        self.assertEqual(std["tokens"], {"input": 3_000_010, "output": 100_000, "cache_write": 200_000,
                                         "cache_read": 3_000_000})
        self.assertEqual(std["wall_clock_seconds"], 155)
        # F: 3 + 15 = 18.
        self.assertEqual(self.report()["spec"]["dollars"], 21.0)  # plus H: 3

    def test_changing_a_price_changes_the_dollars(self):
        dearer = {**PRICES, "m-opus": {**PRICES["m-opus"], "input": 30}}
        # A: 30 + 7.5 + 3.75 + 4.5 = 45.75.  B: 60.
        self.assertEqual(self.report(dearer)["standards"]["dollars"], 105.75)

    def test_value_per_dollar_uses_only_rows_with_known_cost_and_findings(self):
        # A (3) + its over-engineering E (1) + B (1) over 60.75. C (unknown cost) and D (unpriced) are left out,
        # and so are their over-engineering rows E3 and E4: the OE cost is inside the standards dollars, so
        # its value belongs in the same numerator, and only when the standards row itself is counted.
        self.assertEqual(self.report()["standards"]["value_per_dollar"], round(5 / 60.75, 4))
        # F: 3 / k=2 = 1.5 over 18 dollars; G has no cost, and H has cost but unknown findings.
        self.assertEqual(self.report()["spec"]["value_per_dollar"], round(1.5 / 18, 4))

    def test_unknown_and_unpriced_rows_are_counted_never_averaged_as_zero(self):
        std = self.report()["standards"]
        self.assertEqual((std["unknown_cost_rows"], std["unpriced_rows"]), (1, 1))
        spec = self.report()["spec"]
        self.assertEqual(spec["unknown_cost_rows"], 1)

    def test_rows_on_an_unpriced_model_are_named_in_a_note(self):
        self.report()
        self.assertTrue(any(n.startswith("standards: 1 row(s)") for n in self.notes), self.notes)

    def test_no_price_table_means_no_dollars_not_zero_dollars(self):
        std = self.report(None)["standards"]
        self.assertIsNone(std["dollars"])
        self.assertIsNone(std["value_per_dollar"])
        self.assertIn("n/a", self.report(None, fmt="md"))

    def test_over_engineering_cost_is_inside_standards(self):
        oe = self.report()["over-engineering"]
        self.assertEqual(oe["cost_note"], "inside standards")
        self.assertIsNone(oe["dollars"])
        self.assertIsNone(oe["value_per_dollar"])
        self.assertEqual(oe["unknown_cost_rows"], 0)
        self.assertEqual(oe["value"], 1.0 + 3.0 + 3.0)  # E + E3 + E4: reported apart in the value column
        line = next(x for x in self.report(fmt="md").splitlines() if x.startswith("| over-engineering"))
        self.assertIn("inside standards", line)

    def test_markdown_table_carries_the_cost_columns(self):
        head = self.report(fmt="md").splitlines()[0]
        for col in ("tokens", "wall clock", "dollars", "value per dollar"):
            self.assertIn(col, head)
        line = next(x for x in self.report(fmt="md").splitlines() if x.startswith("| spec"))
        self.assertIn("$21.00", line)


class ReportTest(Case):
    def report(self, *extra, rows=None):
        ledger = self.tmp / "in.jsonl"
        write_jsonl(ledger, rows or report_rows())
        result = run("report", "--ledger", ledger, "--format", "json", *extra, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {t["type"]: t for t in json.loads(result.stdout)["types"]}

    COUNT_COLUMNS = ("type", "rows", "findings", "value", "unique_share", "leftover_rate", "dispute_rate",
                     "unknown_outcomes", "unweighted", "unknown_finding_rows", "unknown_cost_rows")

    def count_columns(self, t):
        return {k: t[k] for k in self.COUNT_COLUMNS}

    def test_table_matches_hand_computed_values(self):
        types = self.report()
        self.assertEqual(self.count_columns(types["standards"]), {
            "type": "standards", "rows": 1, "findings": 5, "value": 3.5,
            "unique_share": 0.8, "leftover_rate": 0.25, "dispute_rate": 0.25,
            "unknown_outcomes": 1, "unweighted": 0, "unknown_finding_rows": 1,
            "unknown_cost_rows": 1})
        self.assertEqual(self.count_columns(types["spec"]), {
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
        self.assertIn("| standards | 1 | 5 | 3.50 | 80.0% | 25.0% | 25.0% | 1 | 0 | 1 | 1 "
                      "| n/a | n/a | n/a | n/a | n/a | n/a |", lines)
        self.assertIn("Reviews before #1270 carry no mutation data", result.stdout)
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

    def test_a_prices_file_that_is_not_an_object_fails_loud(self):
        ledger, prices = self.tmp / "in.jsonl", self.tmp / "p.json"
        write_jsonl(ledger, report_rows())
        prices.write_text("[1, 2]")
        result = run("report", "--ledger", ledger, "--prices", prices, home=self.home)
        self.assertEqual(result.returncode, 2)

    def test_missing_ledger_fails_loud(self):
        result = run("report", "--ledger", self.tmp / "absent.jsonl", home=self.home)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
