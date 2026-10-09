"""End-to-end test for spec #1357 (ration the Codex pass by PR size, with a weekly audit of the
PRs that skipped it), closing ticket #1386.

One repo's week, driven through every command the spec's slices built, in the order a controller
uses them. Each step reads what the step before it wrote; every expected number is worked by hand
from the fixture, never read back from the module:

  1. The merge gate on four PRs, each measured from its own branch against `main` and then squash
     merged (#1358, #1359):
       PR #101, ticket 11: 120 counted lines beside 600 lines of tests and Markdown, usage 40%
         -> 40, `under size threshold (120 < 300)`, recorded as a `codex-gate` skip row, reason `size`.
       PR #102, ticket 12: 50 counted lines, ticket labelled `needs-codex`, usage 40%
         -> 0, a proceed: the label forces the pass past the size check. No skip row.
       PR #103, ticket 13: exactly 300 counted lines, usage 75%
         -> 20, `usage 75% at or above reserve ceiling 70%`, a skip row, reason `ceiling`.
       PR #104, ticket 14: 50 counted lines, labelled `needs-codex`, usage 75%
         -> 20 at the ceiling: the label lifts the size check only. A skip row, reason `ceiling`.
     With the kill switch present the same gate answers 20 for every PR, before the size check.
  2. The third pass is gone (#1360): `review_ledger.py append --type codex-third` refuses, and a
     `codex-second` skip row is still accepted.
  3. The weekly audit (#1361, #1362), usage still 75%: `--audit` lifts the ceiling, the range is the
     three skipped PRs and not #102 (which had its pass), the dry run's finding is attributed to the
     audited PR that touched its file, one `codex-audit` ledger row lists the three PRs, and the
     `next:` line names the newest merge.
  4. `mark` moves the audit mark to that sha; the next run finds nothing and stops with 3, recording
     a `codex-audit` skip row with reason `empty`. At 100% usage the audit stops at the gate with 20,
     recording a skip row with the gate's cap line: `--audit` lifts the ceiling, never the cap.
  5. `review_ledger.py report --format json` counts what the week wrote: three `codex-gate` rows, all
     skipped (#102's launched pass is not run here, so it writes none); three `codex-audit` rows, two
     skipped, three audited PRs.

Seam: `bash tests/all.sh`, which runs this file under pytest. HOME, CODEX_HOME, the ledger, the review cache and
the trial doc are temporary, `gh` and `codex` are fakes on PATH, and the Codex launch is the audit's
own `--dry-run`, so nothing reaches the real kill switch, `~/.cache`, GitHub or the Codex quota.

Blind to: anything a human reads rather than a test asserts: whether a model follows a skill's
prose, whether a present `SKILL.md` instruction is also unambiguous, and the harness behaviours
around them (a hook denying a step, a worker spinning on no-op tool calls, a pane closing before a
question is answered, #925). So a green run here does not show that a controller at `implement/
SKILL.md` § The merge step 3 runs the gate with `--base` and `--tickets`, comments its line on the
PR and appends the skip row with `--skip-reason size` or `ceiling` exactly; that the real usage
cache and the real `gh` answer as these fakes do; that a real Codex run's output parses; or that
the controller running the audit confirms and files its findings per `implement/codex-audit.md`.
The rest is the closing ticket's two opens of the real
thing: the gate line on a real heavy PR, and `codex-audit.py run --dry-run` against a copy of the
real ledger.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "implement"))
from codex_audit_fixtures import AuditEnv  # noqa: E402
from codex_audit_test import FINDINGS_OUT  # noqa: E402

GATE = ROOT / "implement" / "codex-usage-gate.py"
AUDIT = ROOT / "implement" / "codex-audit.py"
LEDGER_CLI = ROOT / "docs" / "research" / "review_ledger.py"
WEEK = "2026-09-2{}T12:00:00+00:00"


def lines(n, tag):
    return "".join(f"{tag} line {i}\n" for i in range(n))


class Week(AuditEnv):
    """The audit environment plus this week's drivers: open, gate and merge a PR; run a CLI."""

    def pr(self, pr, ticket, files, labels=(), day=1):
        """Open PR `pr` for `ticket` on its own branch with `files` ({path: line count}), run the merge
        gate on it from there as § The merge step 3 does, then squash-merge it onto main.
        Returns (gate exit, gate line, merge sha)."""
        self.issues[str(ticket)] = {"body": f"Ticket {ticket}.", "comments": [],
                                    "labels": [{"name": n} for n in labels]}
        self.git("checkout", "-q", "-b", f"pr-{pr}", "main")
        for path, n in files.items():
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(lines(n, path))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"work for {ticket}", date=WEEK.format(day))
        gate = self.run_cli(GATE, "--base", "main", "--tickets", str(ticket))
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--squash", f"pr-{pr}")
        self.git("commit", "-q", "-m", f"Work for {ticket} (#{pr})\n\nCloses #{ticket}\n", date=WEEK.format(day))
        self.git("branch", "-q", "-D", f"pr-{pr}")
        return gate.returncode, gate.stdout.strip(), self.git("rev-parse", "HEAD")

    def run_cli(self, script, *args):
        env = {**self.env, "FAKE_ISSUES": json.dumps(self.issues)}
        return subprocess.run([sys.executable, script, *map(str, args)], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def append(self, *args):
        return self.run_cli(LEDGER_CLI, "append", "--repo", "skills", "--ledger", self.ledger, *args)

    def skip(self, ticket, reason):
        r = self.append("--ticket", ticket, "--type", "codex-gate", "--skip-reason", reason)
        assert r.returncode == 0, r.stderr


@pytest.fixture
def week(tmp_path):
    return Week(tmp_path)


def test_a_week_of_rationed_gates_then_the_audit_of_what_they_skipped(week):
    w = week
    # 1. The merge gate, one PR at a time.
    status, line, m101 = w.pr(101, 11, {"lib/a.py": 120, "lib/a_test.py": 200, "tests/t.sh": 200,
                                           "docs/a.md": 200})
    assert (status, line) == (40, "under size threshold (120 < 300)")
    w.skip(11, "size")

    status, line, _ = w.pr(102, 12, {"lib/b.py": 50}, labels=["needs-codex"], day=2)
    assert status == 0, line
    assert "codex usage 40% — ok" in line

    w.set_usage(75)
    status, line, m103 = w.pr(103, 13, {"lib/c.py": 300}, day=3)
    assert status == 20, line
    assert line.startswith("usage 75% at or above reserve ceiling 70%, resets "), line
    w.skip(13, "ceiling")

    status, line, m104 = w.pr(104, 14, {"lib/d.py": 50}, labels=["needs-codex"], day=4)
    assert status == 20, line
    assert "reserve ceiling 70%" in line
    w.skip(14, "ceiling")

    # The kill switch answers before the size check: even a small PR reads 20, never 40.
    w.git("checkout", "-q", "-b", "pr-105", "main")
    (w.repo / "lib" / "e.py").write_text(lines(10, "e"))
    w.git("add", "-A")
    w.git("commit", "-q", "-m", "small")
    w.issues["15"] = {"body": "", "comments": [], "labels": []}
    w.kill_switch()
    r = w.run_cli(GATE, "--base", "main", "--tickets", "15")
    assert r.returncode == 20, r.stdout
    assert "codex reviews off" in r.stdout
    (w.tmp / ".config" / "agent-skills" / "codex-reviews-off").unlink()
    w.git("checkout", "-q", "main")
    w.git("branch", "-q", "-D", "pr-105")

    # 2. The second pass is final: no third-pass row can be written, a second-pass one can.
    r = w.append("--ticket", 12, "--type", "codex-third", "--skip-reason", "x")
    assert r.returncode != 0
    assert "retired" in r.stderr
    r = w.append("--ticket", 12, "--type", "codex-second", "--skip-reason", "ceiling")
    assert r.returncode == 0, r.stderr

    # 3. The weekly audit, still at 75%: the ceiling is lifted for it, and it reviews exactly the
    # three PRs that skipped their gate.
    out = w.tmp / "findings.out"
    out.write_text(FINDINGS_OUT.replace("(a:3-9)", "(lib/c.py:3-9)"))
    r = w.run_cli(AUDIT, "run", "--base", "main", "--ledger", w.ledger, "--cache", w.cache,
                     "--trial", w.trial, "--dry-run", "--simulate-out", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"audit range {w.root}..{m104}: PR #101, PR #103, PR #104\n" in r.stdout
    assert "PR #102" not in r.stdout
    assert ("finding 1 [high] The gate reads an absent answer as a pass (lib/c.py) — "
            "PR #103 ticket #13") in r.stdout
    assert (f"next: confirm and file each finding (implement/codex-audit.md), then "
            f"`codex-audit.py mark --sha {m104}`") in r.stdout
    [audit] = w.rows("codex-audit")
    assert audit["prs"] == [101, 103, 104]
    assert audit["range"] == f"{w.root}..{m104}"
    brief = next(w.cache.glob("codex-audit-*-brief.md")).read_text()
    for pr, ticket, reason in ((101, 11, "size"), (103, 13, "ceiling"), (104, 14, "ceiling")):
        assert f"- PR #{pr} (ticket #{ticket}, skipped for {reason})" in brief

    # 4. The mark moves to the newest audited merge; the next run has nothing to audit.
    r = w.run_cli(AUDIT, "mark", "--sha", m104, "--date", "2026-09-25", "--trial", w.trial)
    assert r.returncode == 0, r.stderr
    assert f"- skills: 2026-09-25 {m104}" in w.trial.read_text()
    r = w.run_cli(AUDIT, "run", "--base", "main", "--ledger", w.ledger, "--cache", w.cache,
                     "--trial", w.trial, "--dry-run")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "nothing to audit" in r.stdout
    assert [a["skip_reason"] for a in w.rows("codex-audit")[1:]] == ["empty"]
    w.set_usage(100)
    r = w.run_cli(AUDIT, "run", "--base", "main", "--ledger", w.ledger, "--cache", w.cache,
                     "--trial", w.trial, "--dry-run")
    assert r.returncode == 20, r.stdout + r.stderr
    assert "codex usage 100% — capped" in r.stdout
    assert "codex usage 100% — capped" in w.rows("codex-audit")[2]["skip_reason"]

    # 5. The report counts the week.
    r = w.run_cli(LEDGER_CLI, "report", "--ledger", w.ledger, "--format", "json")
    assert r.returncode == 0, r.stderr
    by_type = {t["type"]: t for t in json.loads(r.stdout)["types"]}
    assert (by_type["codex-gate"]["rows"], by_type["codex-gate"]["skipped_rows"]) == (3, 3)
    assert (by_type["codex-audit"]["rows"], by_type["codex-audit"]["skipped_rows"],
            by_type["codex-audit"]["audited_prs"]) == (3, 2, 3)
