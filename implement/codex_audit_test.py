#!/usr/bin/env python3
"""Tests for `codex-audit.py` (#1362): the weekly Codex audit's run, from the usage gate through
the ledger row, and the audit mark it reads and moves. Every test drives the command line against a
fabricated repo, ledger, usage cache, trial doc and `gh`, with `--dry-run` in place of the Codex
launch, so nothing reaches the real ~/.cache, the real kill switch, GitHub or the Codex quota."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "codex-audit.py"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

# A `gh` that answers `issue view <n> ... --json body,comments` from FAKE_ISSUES, and fails on
# anything else, so a call the script was not meant to make shows up as a failure.
FAKE_GH = """#!{py}
import json, os, sys
a = sys.argv[1:]
issues = json.loads(os.environ.get("FAKE_ISSUES", "{{}}"))
if a[:2] == ["issue", "view"] and a[2] in issues:
    print(json.dumps(issues[a[2]]))
    sys.exit(0)
print("fake gh: no answer for " + " ".join(a), file=sys.stderr)
sys.exit(1)
"""
# A `codex` that never answers, so the gate's live `--percent` read is `unknown`, never a real RPC.
FAKE_CODEX = "#!/bin/sh\nexit 1\n"

TRIAL_HEAD = """# Codex adversarial-review trial (#812)

**Audit marks (#1362).** One line per audited repo.

{marks}

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | a row |
"""

FINDINGS_OUT = """Verdict: needs-attention

Findings:
- [high] The gate reads an absent answer as a pass (a:3-9)
- [medium] A helper nobody calls (g)

Next steps:
- fix them
"""


def skip_row(ticket, reason, repo="skills"):
    """A gate skip row as `review_ledger.py append --skip-reason` writes it."""
    return {"row_id": f"{repo}/{ticket}/codex-gate/1/codex-skipped-{ticket}-gate", "origin": "append",
            "repo": repo, "ticket": ticket, "tickets": [ticket], "type": "codex-gate", "findings": [],
            "skip_reason": reason,
            "status": {"fields": {"findings": {"status": "skipped", "reason": reason}}}}


def usage_cache(pct):
    now = time.time()
    return {"fetchedAt": now,
            "primary": {"usedPercent": pct, "windowDurationMins": 10080, "resetsAt": now + 3 * 86400},
            "secondary": None}


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, text in (("gh", FAKE_GH.format(py=sys.executable)), ("codex", FAKE_CODEX)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        self.issues = {}
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.tmp), "CODEX_HOME": str(self.codex_home),
                    "PATH": f"{self.bin}:{os.environ['PATH']}"}
        self.repo = self.tmp / "skills"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", "https://github.com/caneff/skills.git")
        self.root = self.commit("root", "f", "2026-09-01T00:00:00+00:00")
        self.ledger = self.tmp / "ledger.jsonl"
        self.ledger.write_text("")
        self.cache = self.tmp / "cache"
        self.trial = self.tmp / "trial.md"
        self.set_mark(f"- skills: 2026-09-01 {self.root}")
        self.set_usage(40)

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, date=None):
        env = {**self.env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
        return subprocess.run(["git", *args], cwd=self.repo, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message, path, date):
        (self.repo / path).write_text(message)
        self.git("add", path)
        self.git("commit", "-q", "-m", message, date=date)
        return self.git("rev-parse", "HEAD")

    def merge(self, pr, ticket, path, date):
        """A squash merge as GitHub writes it, touching `path`; its ticket is readable through `gh`."""
        self.issues[str(ticket)] = {"body": f"Ticket {ticket} asks for {path}.", "comments": []}
        return self.commit(f"Work for {ticket} (#{pr})\n\nCloses #{ticket}\n", path, date)

    def set_mark(self, line):
        self.trial.write_text(TRIAL_HEAD.format(marks=line))

    def set_usage(self, pct):
        (self.codex_home / "usage-cache.json").write_text(json.dumps(usage_cache(pct)))

    def kill_switch(self):
        d = self.tmp / ".config" / "agent-skills"
        d.mkdir(parents=True)
        (d / "codex-reviews-off").write_text("")

    def write_ledger(self, rows):
        self.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def rows(self, kind="codex-audit"):
        return [r for r in map(json.loads, self.ledger.read_text().splitlines()) if r.get("type") == kind]

    def run_audit(self, *extra):
        env = {**self.env, "FAKE_ISSUES": json.dumps(self.issues)}
        return subprocess.run([sys.executable, SCRIPT, "run", "--base", "main", "--ledger", self.ledger,
                               "--cache", self.cache, "--trial", self.trial, "--dry-run", *extra],
                              cwd=self.repo, env=env, capture_output=True, text=True)


class GateStopsTest(Case):
    def test_the_kill_switch_stops_the_run_and_records_a_skip_row(self):
        self.write_ledger([skip_row(11, "size")])
        self.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
        self.kill_switch()
        r = self.run_audit()
        self.assertEqual(r.returncode, 20, r.stderr)
        self.assertIn("codex reviews off", r.stdout)
        [row] = self.rows()
        self.assertIn("codex reviews off", row["skip_reason"])
        self.assertFalse(list(self.cache.glob("codex-audit-*.json")), "a stopped audit has no record")

    def test_an_unknown_usage_reading_stops_the_run_and_records_a_skip_row(self):
        (self.codex_home / "usage-cache.json").unlink()
        r = self.run_audit()
        self.assertEqual(r.returncode, 30, r.stderr)
        [row] = self.rows()
        self.assertIn("codex usage unknown", row["skip_reason"])

    def test_usage_above_the_reserve_ceiling_does_not_stop_the_audit(self):
        self.set_usage(95)  # a PR pass stops at 70 %; the audit may spend the reserve
        r = self.run_audit()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)


class RangeStopsTest(Case):
    def test_nothing_skipped_since_the_mark_stops_the_run_and_records_a_skip_row(self):
        self.write_ledger([skip_row(11, "size")])
        merged = self.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
        self.set_mark(f"- skills: 2026-09-27 {merged}")  # already audited
        r = self.run_audit()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("no skipped PRs since the mark", r.stdout)
        [row] = self.rows()
        self.assertEqual(row["skip_reason"], "empty")

    def test_a_repo_with_no_mark_line_stops_and_names_the_line_to_write(self):
        self.set_mark("- sudokupad-art: 2026-09-01 " + "0" * 40)
        r = self.run_audit()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no audit mark for skills", r.stderr)
        self.assertIn("codex-audit.py mark --sha", r.stderr)
        [row] = self.rows()
        self.assertIn("no audit mark for skills", row["skip_reason"])


class DryRunTest(Case):
    def setUp(self):
        super().setUp()
        self.size = self.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
        self.merge(102, 12, "b", "2026-09-27T12:00:00+00:00")  # its gate pass ran
        self.ceiling = self.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
        self.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
        self.span = f"{self.root}..{self.ceiling}"

    def record(self):
        [path] = self.cache.glob("codex-audit-*.json")
        return json.loads(path.read_text())

    def test_a_clean_run_records_the_range_and_its_prs_and_says_no_findings(self):
        r = self.run_audit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"audit range {self.span}: PR #101, PR #104", r.stdout)
        self.assertIn("no material findings", r.stdout)
        rec = self.record()
        self.assertEqual((rec["prs"], rec["range"], rec["status"]), ([101, 104], self.span, 0))
        [row] = self.rows()
        self.assertEqual((row["prs"], row["range"]), ([101, 104], self.span))
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "known")
        self.assertNotIn("codex-audit-", self.git("worktree", "list"), "the launch worktree is removed")
        self.assertFalse(list(self.cache.glob("*-tree")), "the launch worktree is removed")

    def test_the_brief_renders_every_audited_ticket_then_the_controller_appendix(self):
        self.issues["14"]["comments"] = [{"author": {"login": "caneff"}, "createdAt": "2026-09-28T00:00:00Z",
                                          "isMinimized": False, "body": "Also cover d."}]
        self.assertEqual(self.run_audit().returncode, 0)
        [brief] = self.cache.glob("codex-audit-*-brief.md")
        text = brief.read_text()
        order = [text.index(s) for s in ("Ticket 11 asks for a.", "Ticket 14 asks for c.", "> Also cover d.",
                                         "## Controller context", "**Open sibling branches.**", "**Posture.**")]
        self.assertEqual(order, sorted(order), text)
        self.assertNotIn("Ticket 12", text, "a PR that had its gate pass is not briefed")
        self.assertEqual(self.record()["body_sha256"], __import__("hashlib").sha256(brief.read_bytes()).hexdigest())

    def test_findings_print_with_the_audited_prs_that_touched_their_file(self):
        out = self.tmp / "findings.out"
        out.write_text(FINDINGS_OUT)
        r = self.run_audit("--simulate-out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("finding 1 [high] The gate reads an absent answer as a pass (a) — PR #101 ticket #11", r.stdout)
        self.assertIn("finding 2 [medium] A helper nobody calls (g) — no audited PR touched g", r.stdout)
        [row] = self.rows()
        self.assertEqual(len(row["findings"]), 2)

    def test_a_codex_run_that_exits_non_zero_is_a_refusal_and_the_mark_stays(self):
        r = self.run_audit("--simulate-status", "1")
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("refused", r.stdout)
        self.assertIn("the audit mark does not move", r.stderr)
        [row] = self.rows()
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "refused")
        self.assertIn(f"- skills: 2026-09-01 {self.root}", self.trial.read_text())

    def test_output_that_reads_as_no_findings_section_stops_unreadable(self):
        out = self.tmp / "garbled.out"
        out.write_text("Codex crashed halfway\n")
        r = self.run_audit("--simulate-out", out)
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("read it yourself", r.stdout)
        [row] = self.rows()
        self.assertEqual(row["status"]["fields"]["findings"]["status"], "unknown")

    def test_a_ticket_gh_cannot_read_stops_before_the_launch(self):
        del self.issues["14"]
        r = self.run_audit()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse(list(self.cache.glob("codex-audit-*.json")), "nothing launched, so no record")
        [row] = self.rows()
        self.assertIn("ticket #14", row["skip_reason"])

    def test_a_dry_run_refuses_to_default_to_the_real_ledger(self):
        r = subprocess.run([sys.executable, SCRIPT, "run", "--dry-run", "--cache", self.cache],
                           cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--dry-run needs --ledger and --cache", r.stderr)


class MarkTest(Case):
    def mark(self, *extra):
        return subprocess.run([sys.executable, SCRIPT, "mark", "--trial", self.trial, *extra],
                              cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_mark_moves_this_repos_line_and_leaves_the_others(self):
        other = "- sudokupad-art: 2026-09-01 " + "0" * 40
        self.set_mark(f"- skills: 2026-09-01 {self.root}\n{other}")
        newest = self.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
        r = self.mark("--sha", newest, "--date", "2026-10-09")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.trial.read_text()
        self.assertIn(f"- skills: 2026-10-09 {newest}\n{other}\n", text)
        self.assertNotIn(self.root, text)

    def test_the_next_run_starts_after_the_moved_mark(self):
        self.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
        newest = self.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
        self.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
        self.assertEqual(self.run_audit().returncode, 0)
        self.assertEqual(self.mark("--sha", newest).returncode, 0)
        r = self.run_audit()
        self.assertEqual(r.returncode, 3, r.stdout)

    def test_mark_refuses_a_sha_that_does_not_descend_from_the_current_mark(self):
        newest = self.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
        self.set_mark(f"- skills: 2026-09-30 {newest}")
        r = self.mark("--sha", self.root)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not descend from the current mark", r.stderr)
        self.assertIn(newest, self.trial.read_text())

    def test_mark_refuses_a_sha_that_is_not_a_commit_here(self):
        r = self.mark("--sha", "f" * 40)
        self.assertEqual(r.returncode, 2)
        self.assertIn(self.root, self.trial.read_text())

    def test_mark_refuses_a_date_the_next_run_could_not_read(self):
        r = self.mark("--sha", self.root, "--date", "Oct 9")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--date", r.stderr)
        self.assertIn(f"- skills: 2026-09-01 {self.root}", self.trial.read_text())

    def test_mark_adds_a_line_for_a_repo_never_audited(self):
        other = "- sudokupad-art: 2026-09-01 " + "0" * 40
        self.set_mark(other)
        r = self.mark("--sha", self.root, "--date", "2026-10-03")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{other}\n- skills: 2026-10-03 {self.root}\n", self.trial.read_text())


if __name__ == "__main__":
    unittest.main()
