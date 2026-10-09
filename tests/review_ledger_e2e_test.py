"""End-to-end test for spec #1262 (the review ledger), closing ticket #1302.

One review cache and one transcripts tree, driven through every subcommand the
spec's slices built, in the order the ledger is used. Each step reads what the
step before it wrote; every expected number below is worked by hand from the
fixture, never read back from the module:

  1. `harvest` backfills PR 700 from its sidecars and transcripts: three Claude
     axes, an over-engineering finding inside the standards report, a Codex gate
     pass, a finding two axes both raised (marked shared on both, worth 1/2 each),
     a disputed finding, a leftover, and each axis's tokens and wall clock (#1265,
     #1266, #1267).
  2. `append` writes the forward rows a review step writes when it ends: a spec
     axis (702), a verification pass (701), a Codex pass with its usage change
     (701), a Codex pass skipped at the limit (701), and every mutation type (#1268,
     #1269, #1270). An `append` whose cost source is missing exits non-zero and
     leaves the ledger as it was.
  3. `harvest` over the finished cache and every `append` a second time leave the
     same rows: a run is keyed, so it cannot count twice.
  4. `report` prints the per-type table: weighted value, the 1/k overlap split,
     leftover and dispute rates, unknown counts, dollars from the price table, value
     per dollar, the Codex usage change, skipped passes, and mutation red rates (#1265).

Seam: `bash tests/all.sh`, which runs this file. HOME is a temp dir and every path
is passed explicitly, so nothing reads the real `~/.cache` or `~/.claude/projects`.

Blind to: anything a human reads rather than a test asserts: whether a model
follows a skill's prose, whether a present `SKILL.md` instruction is also
unambiguous, and the harness behaviours around them (a hook denying a step, a
worker spinning on no-op tool calls, a pane closing before a question is answered,
#925). So a green run here does not show that a diff-reviewer axis or the
verification pass actually ends by running `append`, that a controller writes one
`codex-<phase>` row per pass at merge, or that a worker and the correctness
reviewer record their mutations: only that every command those steps name does
what the step relies on. The rest is the closing ticket's
three opens of the real thing, read off `~/.cache/agent-reviews/ledger.jsonl`.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "docs" / "research"
sys.path.insert(0, str(RESEARCH))
from review_ledger_support import (OUT_TWO, SKILLS_PROJ, Env, finding, put, transcript, usage, wt,  # noqa: E402
                                   write_jsonl)

MODEL = "claude-opus-5-5"
# Dollars per million tokens: input, output, cache write, cache read.
PRICES = {MODEL: {"input": 10, "output": 50, "cache_write": 12.5, "cache_read": 1}}
WINDOW = 1790000000
STARTED, COMPLETED = "2026-09-30T09:00:00-04:00", "2026-09-30T09:02:30-04:00"


def leftover(fid, file, title):
    return {"id": fid, "outcome": "leftover", "file": file, "title": title, "severity": "judgement", "text": "kept"}


def fixed(fid):
    return {"id": fid, "outcome": "fixed", "sha": "abc1234"}


class LedgerEndToEnd(Env):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.cache, self.tr = self.tmp / "cache", self.tmp / "projects"
        self.skills = self.cache / "skills"
        self.prices = self.tmp / "prices.json"
        self.prices.write_text(json.dumps(PRICES))

    def ok(self, *args):
        r = self.run(*args)
        assert r.returncode == 0, r.stderr
        return r

    def append(self, *args):
        """Each type takes only the sources it reads: transcripts for a Claude review, the cache for a
        Claude or Codex review, neither for a mutation or a skipped pass."""
        rtype = args[args.index("--type") + 1]
        sources = []
        if not rtype.endswith("mutation") and "--skip-reason" not in args:
            sources += ["--cache", self.cache]
        if rtype in ("spec", "standards", "correctness", "verification"):
            sources += ["--transcripts", self.tr]
        return self.run("append", "--repo", "skills", "--ledger", self.ledger, *sources, *args)

    # -- fixtures ----------------------------------------------------------------

    def build_pr_700(self):
        """One PR: S1 and P1 are the same finding, raised by two axes."""
        s = self.skills
        write_jsonl(s / "findings-standards-700.jsonl", [
            finding("S1", "hard", "a.py", "Duplicated helper loader"),
            finding("OE1", "judgement", "c.py", "Unneeded wrapper class")])
        write_jsonl(s / "findings-spec-700.jsonl", [
            finding("P1", "hard", "a.py", "duplicated loader helper", axis="spec"),
            finding("P2", "judgement", "d.py", "Missing test", axis="spec")])
        write_jsonl(s / "findings-correctness-700.jsonl", [
            finding("C1", "hard", "e.py", "Crash on empty input", axis="correctness"),
            finding("C2", "judgement", "f.py", "Stale docstring", axis="correctness")])
        write_jsonl(s / "dispositions-700.jsonl", [
            fixed("S1"), fixed("OE1"), fixed("P1"),
            {"id": "P2", "outcome": "disputed", "reason": "unreachable here"},
            fixed("C1"), leftover("C2", "f.py", "Stale docstring"),
            fixed("codex-gate-1"), leftover("codex-gate-2", "flow/install.sh", "Prefix match")])
        put(s, 700, "gate", STARTED, COMPLETED, OUT_TWO)
        p700 = wt(SKILLS_PROJ, 700)
        transcript(self.tr, p700, "std", "Standards axis review of #700 diff", "Axis: **Standards**. Repo: x", [
            ("2026-09-30T08:00:00.000Z", "m1", usage(1000, 500, 2000, 10000)),
            ("2026-09-30T08:05:00.000Z", "m2", usage(0, 0, 0, 0))])
        transcript(self.tr, p700, "spec", "Spec review #700", "Repo: x", [
            ("2026-09-30T08:00:00.000Z", "m1", usage(2000, 1000, 0, 0)),
            ("2026-09-30T08:01:00.000Z", "m2", usage(0, 0, 0, 0))])
        transcript(self.tr, p700, "cor", "Reviewer", "Axis: correctness. Repo: x", [
            ("2026-09-30T08:00:00.000Z", "m1", usage(1000, 500, 0, 0)),
            ("2026-09-30T08:02:00.000Z", "m2", usage(0, 0, 0, 0))])

    def build_forward_files(self):
        """What PRs 701 and 702 leave in the cache before their steps append."""
        s = self.skills
        write_jsonl(s / "findings-spec-702.jsonl", [finding("P1", "hard", "g.py", "Forward spec finding", axis="spec")])
        write_jsonl(s / "dispositions-702.jsonl", [fixed("P1")])
        transcript(self.tr, wt(SKILLS_PROJ, 702), "fwd", "Spec review #702", "Repo: x", [
            ("2026-09-30T10:00:00.000Z", "m1", usage(1000, 1000, 0, 0)),
            ("2026-09-30T10:00:30.000Z", "m2", usage(0, 0, 0, 0))])
        write_jsonl(s / "findings-verify-701.jsonl", [finding("V1", "judgement", "h.py", "Hollow witness", axis="verify")])
        write_jsonl(s / "dispositions-701.jsonl", [
            fixed("V1"), fixed("codex-second-1"),
            {"id": "codex-second-2", "outcome": "disputed", "reason": "unreachable"}])
        transcript(self.tr, wt(SKILLS_PROJ, 701), "ver", "Verification pass", "Verification of round 1", [
            ("2026-09-30T09:00:00.000Z", "m1", usage(1000, 0, 0, 0)),
            ("2026-09-30T09:00:10.000Z", "m2", usage(0, 0, 0, 0))])
        put(s, 701, "second", STARTED, COMPLETED, OUT_TWO)
        rec = s / "codex-adversarial-701-second.json"
        body = json.loads(rec.read_text())
        body.update(usage_before=f"10 {WINDOW}", usage_after=f"12.5 {WINDOW}")
        rec.write_text(json.dumps(body) + "\n")
        (self.tmp / "status").mkdir()
        for mid, text in (("w1", "red\n"), ("w2", "unknown\n"), ("c1", "green\n")):
            (self.tmp / "status" / mid).write_text(text)

    def append_forward_rows(self):
        st = self.tmp / "status"
        return [
            self.append("--ticket", 702, "--type", "spec"),
            self.append("--ticket", 701, "--type", "verification"),
            self.append("--ticket", 701, "--type", "codex-second"),
            self.append("--ticket", 702, "--type", "codex-second", "--skip-reason", "usage capped until 2026-10-03"),
            self.append("--ticket", 701, "--type", "worker-mutation", "--mutation-id", "m1", "--outcome", "red", "--seconds", 20),
            self.append("--ticket", 701, "--type", "worker-mutation", "--mutation-id", "m2", "--outcome", "green", "--seconds", 10),
            self.append("--ticket", 701, "--type", "witness-mutation", "--mutation-id", "w1", "--status-file", st / "w1", "--seconds", 30),
            self.append("--ticket", 701, "--type", "witness-mutation", "--mutation-id", "w2", "--status-file", st / "w2", "--seconds", 5),
            self.append("--ticket", 701, "--type", "call-site-mutation", "--mutation-id", "c1", "--status-file", st / "c1", "--seconds", 15),
        ]


@pytest.fixture
def e2e(tmp_path):
    return LedgerEndToEnd(tmp_path)


# -- the run -----------------------------------------------------------------


def test_backfill_then_forward_rows_then_report(e2e):
    e2e.build_pr_700()
    review = e2e.tmp / "review.md"
    e2e.ok("harvest", "--cache", e2e.cache, "--transcripts", e2e.tr, "--ledger", e2e.ledger,
            "--review-file", review)

    # 1. The backfill: one row per review, a shared finding marked on both reviewers.
    rows = e2e.rows()
    assert sorted(r["type"] for r in rows.values()) == \
        ["codex-gate", "correctness", "over-engineering", "spec", "standards"]
    shared = {f["id"]: f["overlap"] for r in rows.values() for f in r["findings"] if f["id"] in ("S1", "P1", "P2")}
    assert shared["S1"] == shared["P1"]
    assert shared["P1"] != "unique"
    assert shared["P2"] == "unique"
    spec_tokens = rows["skills/700/spec/1/findings-spec-700"]["cost"]["tokens"]
    assert (spec_tokens["status"], spec_tokens["input"], spec_tokens["output"]) == ("known", 2000, 1000)
    # a record with no readings is unknown, never zero
    assert rows["skills/700/codex-gate/1/codex-adversarial-700-gate"]["cost"]["usage_delta"]["status"] == "unknown"

    # 2. Forward rows.
    e2e.build_forward_files()
    before = e2e.ledger.read_text()
    missing = e2e.append("--ticket", 799, "--type", "spec")
    assert missing.returncode != 0
    assert e2e.ledger.read_text() == before, "a refused append must write nothing"
    for r in e2e.append_forward_rows():
        assert r.returncode == 0, r.stderr
    rows = e2e.rows()
    assert len(rows) == 5 + 9
    second = rows["skills/701/codex-second/1/codex-adversarial-701-second"]["cost"]["usage_delta"]
    assert (second["status"], second["delta"]) == ("known", 2.5)
    assert {r["outcome"] for r in rows.values() if r["type"] == "witness-mutation"} == {"red", "unknown"}

    # 3. Rerunning every step leaves the same rows.
    for r in e2e.append_forward_rows():
        assert r.returncode == 0, r.stderr
    e2e.ok("harvest", "--cache", e2e.cache, "--transcripts", e2e.tr, "--ledger", e2e.ledger,
            "--review-file", review)
    # (A row append wrote stays `append` through a harvest, #1304: nothing may differ, origin included.)
    again = e2e.rows()
    assert set(again) == set(rows)
    for row_id, row in rows.items():
        assert again[row_id] == row, row_id

    # 4. The report, every figure worked by hand (default weights: hard 3, judgement 1,
    #    Codex high 3, medium 2, low 1; overlap split 1/k).
    table = json.loads(e2e.ok("report", "--ledger", e2e.ledger, "--prices", e2e.prices,
                               "--format", "json").stdout)["types"]
    got = {t["type"]: t for t in table}
    assert sorted(got) == ["call-site-mutation", "codex-gate", "codex-second", "correctness",
                           "over-engineering", "spec", "standards", "verification", "witness-mutation",
                           "worker-mutation"]

    def check(type_, **want):
        for key, value in want.items():
            assert got[type_][key] == value, f"{type_}.{key}"

    # standards: S1 hard shared with P1 -> 3/2. Cost 1000*10 + 500*50 + 2000*12.5 + 10000*1 = $0.07, 300 s.
    # Its over-engineering finding (judgement, fixed, unique) is worth 1 and costs "inside standards".
    check("standards", rows=1, findings=1, value=1.5, unique_share=0.0, dollars=0.07, wall_clock_seconds=300,
          value_per_dollar=round((1.5 + 1.0) / 0.07, 4), unknown_cost_rows=0)
    check("over-engineering", rows=1, findings=1, value=1.0, cost_note="inside standards")
    # spec 700: P1 3/2 and P2 disputed 0; spec 702: P1 hard unique 3. Cost $0.07 + $0.06, 60 s + 30 s.
    check("spec", rows=2, findings=3, value=4.5, dispute_rate=1 / 3, leftover_rate=0.0, dollars=0.13, wall_clock_seconds=90,
          value_per_dollar=round(4.5 / 0.13, 4))
    assert got["spec"]["unique_share"] == pytest.approx(2 / 3)
    # correctness: C1 hard 3, C2 leftover 0 and its own rate. Cost 1000*10 + 500*50 = $0.035.
    check("correctness", rows=1, findings=2, value=3.0, leftover_rate=0.5, dispute_rate=0.0, dollars=0.035,
          value_per_dollar=round(3 / 0.035, 4))
    # verification: V1 judgement 1, $0.01.
    check("verification", rows=1, findings=1, value=1.0, dollars=0.01, value_per_dollar=100.0)
    # Codex: the gate's high is fixed (3) and its medium left over; the second pass's high is fixed (3), its medium
    # disputed; the second pass cost 12.5 - 10 points of usage. #702's second pass was skipped: a known
    # zero, not a clean pass.
    check("codex-gate", rows=1, findings=2, value=3.0, leftover_rate=0.5, unknown_usage_rows=1, usage_percent=None)
    check("codex-second", rows=2, skipped_rows=1, clean_rows=0, findings=2, value=3.0, dispute_rate=0.5,
          usage_percent=2.5, unknown_usage_rows=0)
    # Mutations: red rate leaves unknown out and counts it beside.
    check("worker-mutation", rows=2, red_rate=0.5, unknown_mutations=0)
    check("witness-mutation", rows=2, red_rate=1.0, unknown_mutations=1)
    check("call-site-mutation", rows=1, red_rate=0.0, unknown_mutations=0)

    # The markdown form carries the same table.
    md = e2e.ok("report", "--ledger", e2e.ledger, "--prices", e2e.prices).stdout
    assert "| standards | 1 | 1 | 1.50 |" in md
    assert "| over-engineering | 1 | 1 | 1.00 |" in md
    assert "inside standards" in md
