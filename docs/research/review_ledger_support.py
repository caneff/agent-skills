"""Fixture builders and command runners shared by the review_ledger and
tally_review_axes suites (#1265, #1494). Every suite runs a subcommand's command
line on a fixture tree and reads what comes out; every run points HOME at a temp
dir so no default path can reach the real ~/.cache or ~/.claude."""
import json
import os
import subprocess
import sys
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


def section(text: str, heading: str) -> str:
    """The body of one `## <heading>` section of the review file."""
    return text.split(f"## {heading}")[1].split("\n## ")[0]


class Env:
    """One test's temp tree: its HOME, the ledger and review file the commands write."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.ledger = tmp / "ledger.jsonl"
        self.review = tmp / "review.md"

    def run(self, *args):
        return run(*args, home=self.home)

    def harvest(self, cache: Path):
        result = self.run("harvest", "--cache", cache, "--ledger", self.ledger,
                          "--review-file", self.review)
        assert result.returncode == 0, result.stderr
        return result

    def rows(self):
        """The ledger's rows by row id; none when no command has written it yet."""
        return {r["row_id"]: r for r in map(json.loads, self.ledger.read_text().splitlines())} \
            if self.ledger.exists() else {}


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


OUT_TWO = """[codex] Starting Codex task thread.
# Codex Adversarial Review

Target: branch diff against origin/main
Verdict: needs-attention

No ship.

Findings:
- [high] Guard breaks first pushes (flow/guard.sh:34-42)
  Body of the first finding (with parens).
  Recommendation: fix it.
- [medium] Prefix match swallows a conflict (flow/install.sh:70)
  Body.

Next steps:
- Fix both.
"""
OUT_CLEAN = """# Codex Adversarial Review

Verdict: approve

Ship.

No material findings.
"""
OUT_REFUSED = """[codex] Turn started (x).
[codex] Codex error: You've hit your usage limit. Try again at Oct 3rd.
[codex] Turn failed.
# Codex Adversarial Review

Codex did not return valid structured JSON.

- Parse error: You've hit your usage limit.
"""
OUT_UNPARSED = """# Codex Adversarial Review

Verdict: needs-attention

Findings:
  something the parser cannot read
"""


def record(ticket, phase, started, completed, status=0):
    return {"ticket": ticket, "phase": phase, "status": status, "launch_sha": "a", "completion_sha": "a",
            "body_sha256": "b", "started": started, "completed": completed}


def put(repo_dir, ticket, phase, started, completed, out, status=0):
    stem = repo_dir / f"codex-adversarial-{ticket}-{phase}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".json").write_text(json.dumps(record(ticket, phase, started, completed, status)) + "\n")
    if out is not None:
        stem.with_suffix(".out").write_text(out)


def build_codex_cache(root):
    skills = root / "skills"
    # 200: all three phases. Gate: two findings, joined to dispositions by number.
    put(skills, 200, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:02:30-04:00", OUT_TWO)
    put(skills, 200, "second", "2026-09-22T09:10:00-04:00", "2026-09-22T09:11:00-04:00", OUT_TWO)
    put(skills, 200, "third", "2026-09-22T09:20:00-04:00", "2026-09-22T09:20:45-04:00", OUT_CLEAN)
    write_jsonl(skills / "dispositions-200.jsonl", [
        {"id": "codex-gate-1", "outcome": "fixed", "sha": "abc"},
        {"id": "codex-gate-2", "outcome": "leftover", "file": "flow/install.sh", "title": "t",
         "severity": "medium", "text": "kept"},
        {"id": "codex-second-H1", "outcome": "disputed", "reason": "unreachable"},
        {"id": "codex-second-M1", "outcome": "filed", "ticket": 9},
        {"id": "codex-third-9", "outcome": "fixed", "sha": "z"},
    ])
    # 201: refused at the usage limit.
    put(skills, 201, "gate", "2026-09-27T14:10:35-04:00", "2026-09-27T14:10:38-04:00", OUT_REFUSED, status=1)
    # 202: findings the parser cannot read; 203: a record with no .out at all.
    put(skills, 202, "gate", "2026-09-22T10:00:00-04:00", "2026-09-22T10:01:00-04:00", OUT_UNPARSED)
    put(skills, 203, "gate", "2026-09-22T11:00:00-04:00", "2026-09-22T11:01:00-04:00", None)
    # 204: a retried gate, an early launch (not one of the three types), and a record
    # whose timestamps do not parse.
    put(skills, 204, "gate-retry", "2026-09-22T12:00:00-04:00", "2026-09-22T12:00:10-04:00", OUT_CLEAN)
    put(skills, 204, "early", "2026-09-22T12:10:00-04:00", "2026-09-22T12:10:10-04:00", OUT_CLEAN)
    put(skills, 205, "gate", "not a time", "2026-09-22T12:10:10-04:00", OUT_CLEAN)
    # 206: a Claude finding matching Codex's first finding: shared credit.
    write_jsonl(skills / "findings-spec-206.jsonl",
                [finding("P1", "hard", "flow/guard.sh", "guard breaks first pushes", axis="spec")])
    write_jsonl(skills / "dispositions-206.jsonl", [{"id": "P1", "outcome": "fixed", "sha": "e"},
                                                   {"id": "codex-gate-1", "outcome": "fixed", "sha": "f"}])
    put(skills, 206, "gate", "2026-09-22T13:00:00-04:00", "2026-09-22T13:01:00-04:00", OUT_TWO)
    # 207: a dispositions line for a Codex pass that has no record in this ticket: stays an orphan
    # although other tickets join the same `codex-gate-1` id.
    write_jsonl(skills / "dispositions-207.jsonl", [{"id": "codex-gate-1", "outcome": "fixed", "sha": "q"}])
    # A scratch directory is not a review directory.
    put(root / "scratch-9", 999, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_TWO)
    # A repo whose cache holds only Codex records.
    put(root / "other", 300, "gate", "2026-09-22T09:00:00-04:00", "2026-09-22T09:01:00-04:00", OUT_CLEAN)

