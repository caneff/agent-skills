"""Tests for `codex-audit.py` (#1362): the weekly Codex audit's run, from the usage gate through
the ledger row, and the audit mark it reads and moves. Every test drives the command line against a
fabricated repo, ledger, usage cache, trial doc and `gh`, with `--dry-run` in place of the Codex
launch, so nothing reaches the real ~/.cache, the real kill switch, GitHub or the Codex quota. Runs under pytest."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_audit_fixtures import AuditEnv, skip_row

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "codex-audit.py"

FINDINGS_OUT = """Verdict: needs-attention

Findings:
- [high] The gate reads an absent answer as a pass (a:3-9)
- [medium] A helper nobody calls (g)
- [low] A finding that names no file

Next steps:
- fix them
"""


@pytest.fixture
def case(tmp_path):
    return AuditEnv(tmp_path)


@pytest.fixture
def dry(case):
    """`case` with three merges, two of them skipped in the ledger (the middle one had its gate pass)."""
    case.size = case.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
    case.merge(102, 12, "b", "2026-09-27T12:00:00+00:00")  # its gate pass ran
    case.ceiling = case.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
    case.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
    case.span = f"{case.root}..{case.ceiling}"
    return case


# --- the gate stops the run


def test_the_kill_switch_stops_the_run_and_records_a_skip_row(case):
    case.write_ledger([skip_row(11, "size")])
    case.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
    case.kill_switch()
    r = case.run_audit()
    assert r.returncode == 20, r.stderr
    assert "codex reviews off" in r.stdout
    [row] = case.rows()
    assert "codex reviews off" in row["skip_reason"]
    assert not list(case.cache.glob("codex-audit-*.json")), "a stopped audit has no record"


def test_an_unknown_usage_reading_stops_the_run_and_records_a_skip_row(case):
    (case.codex_home / "usage-cache.json").unlink()
    r = case.run_audit()
    assert r.returncode == 30, r.stderr
    [row] = case.rows()
    assert "codex usage unknown" in row["skip_reason"]


def test_usage_above_the_reserve_ceiling_does_not_stop_the_audit(case):
    case.set_usage(95)  # a PR pass stops at 70 %; the audit may spend the reserve
    r = case.run_audit()
    assert r.returncode == 3, r.stdout + r.stderr


# --- the range stops the run


def test_nothing_skipped_since_the_mark_stops_the_run_and_records_a_skip_row(case):
    case.write_ledger([skip_row(11, "size")])
    merged = case.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
    case.set_mark(f"- skills: 2026-09-27 {merged}")  # already audited
    r = case.run_audit()
    assert r.returncode == 3, r.stderr
    assert "no skipped PRs since the mark" in r.stdout
    [row] = case.rows()
    assert row["skip_reason"] == "empty"


def test_only_left_out_tickets_stop_as_unmatched_never_as_empty(case):
    case.write_ledger([skip_row(11, "size")])
    case.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
    case.merge(102, 11, "b", "2026-09-27T12:00:00+00:00")  # two merges close #11: undated
    r = case.run_audit()
    assert r.returncode == 6, r.stdout + r.stderr
    [row] = case.rows()
    assert row["skip_reason"] == "left out, unaudited: ticket #11"


def test_two_mark_lines_for_one_repo_stop_the_run(case):
    case.set_mark(f"- skills: 2026-09-01 {case.root}\n- skills: 2026-09-02 {case.root}")
    r = case.run_audit()
    assert r.returncode == 2, r.stdout
    assert "2 audit marks for skills" in r.stderr


def test_a_repo_with_no_mark_line_stops_and_names_the_line_to_write(case):
    case.set_mark("- sudokupad-art: 2026-09-01 " + "0" * 40)
    r = case.run_audit()
    assert r.returncode == 2, r.stdout
    assert "no audit mark for skills" in r.stderr
    assert "codex-audit.py mark --sha" in r.stderr
    [row] = case.rows()
    assert "no audit mark for skills" in row["skip_reason"]


# --- the dry run


def test_a_clean_run_records_the_range_and_its_prs_and_says_no_findings(dry):
    r = dry.run_audit()
    assert r.returncode == 0, r.stderr
    assert f"audit range {dry.span}: PR #101, PR #104" in r.stdout
    assert "no material findings" in r.stdout
    rec = dry.record()
    assert (rec["prs"], rec["range"], rec["status"]) == ([101, 104], dry.span, 0)
    [row] = dry.rows()
    assert (row["prs"], row["range"]) == ([101, 104], dry.span)
    assert row["status"]["fields"]["findings"]["status"] == "known"
    assert "codex-audit-" not in dry.git("worktree", "list"), "the launch worktree is removed"
    assert not list(dry.cache.glob("*-tree")), "the launch worktree is removed"


def test_the_brief_renders_every_audited_ticket_then_the_controller_appendix(dry):
    dry.issues["14"]["comments"] = [{"author": {"login": "caneff"}, "createdAt": "2026-09-28T00:00:00Z",
                                     "isMinimized": False, "body": "Also cover d."}]
    assert dry.run_audit().returncode == 0
    [brief] = dry.cache.glob("codex-audit-*-brief.md")
    text = brief.read_text()
    order = [text.index(s) for s in ("Ticket 11 asks for a.", "Ticket 14 asks for c.", "> Also cover d.",
                                     "## Controller context", "**Open sibling branches.**", "**Posture.**")]
    assert order == sorted(order), text
    assert "Ticket 12" not in text, "a PR that had its gate pass is not briefed"
    assert dry.record()["body_sha256"] == hashlib.sha256(brief.read_bytes()).hexdigest()


def test_findings_print_with_the_audited_prs_that_touched_their_file(dry):
    out = dry.tmp / "findings.out"
    out.write_text(FINDINGS_OUT)
    r = dry.run_audit("--simulate-out", out)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert "finding 1 [high] The gate reads an absent answer as a pass (a) — PR #101 ticket #11" in lines
    assert "finding 2 [medium] A helper nobody calls (g) — no audited PR touched g" in lines
    assert "finding 3 [low] A finding that names no file () — names no file" in lines
    [row] = dry.rows()
    assert len(row["findings"]) == 3


def test_a_codex_run_that_exits_non_zero_is_a_refusal_and_the_mark_stays(dry):
    r = dry.run_audit("--simulate-status", "1")
    assert r.returncode == 4, r.stdout
    assert "refused" in r.stdout
    assert "the audit mark does not move" in r.stderr
    [row] = dry.rows()
    assert row["status"]["fields"]["findings"]["status"] == "refused"
    assert f"- skills: 2026-09-01 {dry.root}" in dry.trial.read_text()


def test_output_that_reads_as_no_findings_section_stops_unreadable(dry):
    out = dry.tmp / "garbled.out"
    out.write_text("Codex crashed halfway\n")
    r = dry.run_audit("--simulate-out", out)
    assert r.returncode == 5, r.stdout
    assert "read it yourself" in r.stdout
    assert f"codex-audit.py mark --sha {dry.ceiling}" in r.stdout, "its findings are filed too"
    [row] = dry.rows()
    assert row["status"]["fields"]["findings"]["status"] == "unknown"


def test_a_ticket_gh_cannot_read_stops_before_the_launch(dry):
    del dry.issues["14"]
    r = dry.run_audit()
    assert r.returncode == 2, r.stdout
    assert not list(dry.cache.glob("codex-audit-*.json")), "nothing launched, so no record"
    [row] = dry.rows()
    assert "ticket #14" in row["skip_reason"]


def test_a_ticket_no_single_merge_closes_is_printed_as_left_out(dry):
    dry.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling"), skip_row(99, "size")])
    r = dry.run_audit()
    assert r.returncode == 0, r.stderr
    assert "left out: ticket #99, not in this audit" in r.stdout
    assert dry.record()["left_out"] == [99]


def test_a_missing_tool_stops_with_a_row_not_a_traceback(dry):
    for tool in ("git", "python3"):  # everything else, `jq` included, is off PATH
        os.symlink(subprocess.run(["which", tool], capture_output=True, text=True).stdout.strip(),
                   dry.bin / tool)
    dry.env["PATH"] = str(dry.bin)
    r = dry.run_audit()
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    [row] = dry.rows()
    assert "jq" in row["skip_reason"]


def test_simulate_flags_without_dry_run_refuse_rather_than_launch(dry):
    r = subprocess.run([sys.executable, SCRIPT, "run", "--ledger", dry.ledger, "--cache", dry.cache,
                        "--trial", dry.trial, "--simulate-status", "0"],
                       cwd=dry.repo, env=dry.env, capture_output=True, text=True)
    assert r.returncode == 2
    assert "are for --dry-run" in r.stderr
    assert dry.rows() == [], "refused before the gate: nothing ran, nothing recorded"


def test_a_dry_run_refuses_to_default_to_the_real_ledger(dry):
    r = subprocess.run([sys.executable, SCRIPT, "run", "--dry-run", "--cache", dry.cache],
                       cwd=dry.repo, env=dry.env, capture_output=True, text=True)
    assert r.returncode == 2
    assert "--dry-run needs --ledger and --cache" in r.stderr


# --- the audit mark


def test_mark_moves_this_repos_line_and_leaves_the_others(case):
    other = "- sudokupad-art: 2026-09-01 " + "0" * 40
    case.set_mark(f"- skills: 2026-09-01 {case.root}\n{other}")
    newest = case.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
    r = case.mark("--sha", newest, "--date", "2026-10-09")
    assert r.returncode == 0, r.stderr
    text = case.trial.read_text()
    assert f"- skills: 2026-10-09 {newest}\n{other}\n" in text
    assert case.root not in text


def test_the_next_run_starts_after_the_moved_mark(case):
    case.merge(101, 11, "a", "2026-09-26T12:00:00+00:00")
    newest = case.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
    case.write_ledger([skip_row(11, "size"), skip_row(14, "ceiling")])
    assert case.run_audit().returncode == 0
    assert case.mark("--sha", newest).returncode == 0
    r = case.run_audit()
    assert r.returncode == 3, r.stdout


def test_mark_refuses_a_sha_that_does_not_descend_from_the_current_mark(case):
    newest = case.merge(104, 14, "c", "2026-09-29T12:00:00+00:00")
    case.set_mark(f"- skills: 2026-09-30 {newest}")
    r = case.mark("--sha", case.root)
    assert r.returncode == 2
    assert "does not descend from the current mark" in r.stderr
    assert newest in case.trial.read_text()


def test_mark_refuses_a_sha_that_is_not_a_commit_here(case):
    case.set_mark("- sudokupad-art: 2026-09-01 " + "0" * 40)  # no skills line, so no descent check
    r = case.mark("--sha", "f" * 40)
    assert r.returncode == 2
    assert "is not a commit in this checkout" in r.stderr
    assert "- skills:" not in case.trial.read_text()


def test_mark_refuses_a_date_the_next_run_could_not_read(case):
    r = case.mark("--sha", case.root, "--date", "Oct 9")
    assert r.returncode == 2
    assert "--date" in r.stderr
    assert f"- skills: 2026-09-01 {case.root}" in case.trial.read_text()


def test_mark_refuses_to_pick_between_two_lines_for_one_repo(case):
    twice = f"- skills: 2026-09-01 {case.root}\n- skills: 2026-09-02 {case.root}"
    case.set_mark(twice)
    r = case.mark("--sha", case.root)
    assert r.returncode == 2
    assert "2 audit marks for skills" in r.stderr
    assert twice in case.trial.read_text()


def test_mark_adds_a_line_for_a_repo_never_audited(case):
    other = "- sudokupad-art: 2026-09-01 " + "0" * 40
    case.set_mark(other)
    r = case.mark("--sha", case.root, "--date", "2026-10-03")
    assert r.returncode == 0, r.stderr
    assert f"{other}\n- skills: 2026-10-03 {case.root}\n" in case.trial.read_text()


# --- the doc's wording: § Close out names the checkout the trial row goes to, so the audit's cwd is
# never the target (#1227)


def close_out():
    text = (HERE / "codex-audit.md").read_text()
    return text.split("## 4. Close out", 1)[1].split("## Dry run", 1)[0]


def test_trial_row_goes_to_the_resolved_skills_checkout():
    section = close_out()
    assert "git -C ~/.agents/skills/implement rev-parse --show-toplevel" in section
    assert "never the working directory" in " ".join(section.split())


def test_no_bare_relative_path_to_the_trial_log():
    lines = [l for l in close_out().splitlines() if "codex-review-trial.md" in l]
    assert lines, "§ Close out no longer names the trial log"
    for line in lines:
        assert "<skills checkout>/docs/research/" in line
