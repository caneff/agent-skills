#!/usr/bin/env python3
"""Tests for pointer_reads.py (#1413): the pointer-doc read count from
docs/research/2026-10-04-claude-md-pointer-reads.md, and the one-shot cron
re-count 14 days after #1413 closes. Every test runs the script's command
line. `gh` and `crontab` are fakes on PATH, the repo is a scratch clone with a
bare origin, and the transcripts are synthetic, so nothing here reads the
real ~/.claude/projects or the real crontab."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("pointer_reads.py")
NOTE = "docs/research/2026-10-04-claude-md-pointer-reads.md"
TAG = "# pointer-reads-recount-1413"


def line(ts, **fields):
    # Transcripts are compact JSON: `"command":"..."` with no space, which is
    # what the 2026-10-04 grep matched.
    row = {"timestamp": ts, **fields} if ts else fields
    return json.dumps(row, separators=(",", ":")) + "\n"


def bash(cmd):
    return {"message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}


def read(path):
    return {"message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": path}}]}}


SKILL = {"message": {"content": "Base directory for this skill: /home/u/.claude/skills/implement"}}


def epoch(iso):
    return datetime.fromisoformat(iso).timestamp()


@pytest.fixture
def projects(tmp_path):
    """End 2026-10-04T12:00Z, so the window is (2026-09-20T12:00Z, end]."""
    root = tmp_path / "count-projects"
    root.mkdir()
    p = root / "-home-u-repo"
    p.mkdir()
    inwin, late, old = "2026-10-01T00:00:00Z", "2026-10-05T00:00:00Z", "2026-09-01T00:00:00Z"
    # a: merge, read OPERATIONS, no skill -> triggered, uncovered, read.
    (p / "a.jsonl").write_text(line(inwin, **bash("gh pr merge 5 --repo o/r"))
                               + line(inwin, **read("/h/.agents/skills/flow/claude/OPERATIONS.md")))
    # b: merge under the implement skill, no read -> triggered, covered.
    (p / "b.jsonl").write_text(line(inwin, **SKILL) + line(inwin, **bash("merge-cleanup x")))
    # c: a kill, but only after the end -> not triggered.
    (p / "c.jsonl").write_text(line(inwin, **bash("ls")) + line(late, **bash("pkill foo")))
    # d: a subagent transcript -> never a session.
    (p / "a" / "subagents").mkdir(parents=True)
    (p / "a" / "subagents" / "d.jsonl").write_text(line(inwin, **bash("gh pr merge 1")))
    # e: every line older than the window -> not a session.
    (p / "e.jsonl").write_text(line(old, **bash("gh issue create -t x")))
    os.utime(p / "e.jsonl", (epoch("2026-09-01T00:00:00+00:00"),) * 2)
    # f: no timestamped line, but modified in the window -> a session.
    (p / "f.jsonl").write_text(line(None, **bash("gh issue edit 3")))
    os.utime(p / "f.jsonl", (epoch("2026-10-02T00:00:00+00:00"),) * 2)
    for n in "abc":
        os.utime(p / f"{n}.jsonl", (epoch("2026-10-05T00:00:00+00:00"),) * 2)
    return root


def test_count_tables(projects):
    out = subprocess.run([sys.executable, str(SCRIPT), "count", "--end", "2026-10-04T12:00:00Z",
                          "--projects", str(projects)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert "Sessions in the window: 4" in text
    assert "| OPERATIONS | `gh pr merge\\|implement-dispatch\\|merge-cleanup` | 2 | 1 |" in text
    assert "| WORKFLOW | `gh issue create\\|gh issue edit` | 1 | 0 |" in text
    assert "| SHELL-SAFETY | `pkill\\|kill -\\|kill [0-9]` | 0 | 0 |" in text
    assert "| OPERATIONS | 2 | 1 | 1 |" in text
    assert "| WORKFLOW | 1 | 1 | 0 |" in text


class Recount:
    """A scratch clone with a bare origin, fake `gh` and `crontab` on PATH, and one synthetic transcript."""

    def __init__(self, tmp):
        self.tmp = tmp
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env = env
        origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        seed = self.tmp / "seed"
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        self.git(seed, "config", "user.email", "t@example.com")
        self.git(seed, "config", "user.name", "t")
        (seed / "docs" / "research").mkdir(parents=True)
        (seed / NOTE).write_text("# note\n")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-q", "-m", "seed")
        self.git(seed, "remote", "add", "origin", str(origin))
        self.git(seed, "push", "-q", "origin", "main")
        self.root = seed
        self.origin = origin
        self.projects = self.tmp / "projects"
        (self.projects / "x").mkdir(parents=True)
        (self.projects / "x" / "s.jsonl").write_text(
            line("2026-10-10T00:00:00Z", **bash("pkill foo")))
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        self.crontab_file = self.tmp / "crontab.txt"
        self.crontab_file.write_text(f"0 8 * * 1 other-job  # other\n17 9 * * * recount {TAG}\n")
        (bin_ / "crontab").write_text(
            "#!/usr/bin/env bash\n"
            f'f="{self.crontab_file}"\n'
            f'm="{self.tmp}/crontab-mode"\n'
            'if [ "${1:-}" = -l ]; then\n'
            '  [ "$(cat "$m" 2>/dev/null)" = none ] && { echo "no crontab for u" >&2; exit 1; }\n'
            '  [ "$(cat "$m" 2>/dev/null)" = broken ] && { echo "cannot open spool" >&2; exit 1; }\n'
            '  cat "$f"\n'
            'elif [ "${1:-}" = - ]; then cat > "$f"; else exit 2; fi\n')
        self.gh_out = self.tmp / "gh.json"
        (bin_ / "gh").write_text(
            "#!/usr/bin/env bash\n"
            f'[ -f "{self.gh_out}" ] || {{ echo "HTTP 502" >&2; exit 1; }}\n'
            f'cat "{self.gh_out}"\n')
        for f in bin_.iterdir():
            f.chmod(0o755)
        self.env["PATH"] = f"{bin_}:{os.environ['PATH']}"

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                              text=True, env=self.env).stdout

    def gh(self, payload):
        self.gh_out.write_text(json.dumps(payload))

    def recount(self, today):
        return subprocess.run([sys.executable, str(SCRIPT), "recount", "--today", today,
                               "--root", str(self.root), "--projects", str(self.projects)],
                              capture_output=True, text=True, env=self.env)

    def origin_note(self):
        return subprocess.run(["git", "--git-dir", str(self.origin), "show", f"main:{NOTE}"],
                              capture_output=True, text=True, env=self.env).stdout


@pytest.fixture
def rc(tmp_path):
    return Recount(tmp_path)


def test_open_ticket_exits_silently(rc):
    rc.gh({"state": "OPEN", "closedAt": None})
    out = rc.recount("2026-12-01T00:00:00Z")
    assert (out.returncode, out.stdout, out.stderr) == (0, "", "")
    assert TAG in rc.crontab_file.read_text()
    assert rc.origin_note() == "# note\n"


def test_before_the_date_exits_silently(rc):
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    out = rc.recount("2026-10-19T11:59:59Z")
    assert (out.returncode, out.stdout, out.stderr) == (0, "", "")
    assert TAG in rc.crontab_file.read_text()
    assert rc.origin_note() == "# note\n"


def test_on_the_date_appends_commits_pushes_and_removes_its_line(rc):
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    out = rc.recount("2026-10-19T12:00:00Z")
    assert out.returncode == 0, out.stdout + out.stderr
    note = rc.origin_note()
    assert "## Re-count 2026-10-19" in note
    assert "2026-10-05T12:00:00Z" in note
    assert "| SHELL-SAFETY | `pkill\\|kill -\\|kill [0-9]` | 1 | 0 |" in note
    cron = rc.crontab_file.read_text()
    assert TAG not in cron
    assert "other-job  # other" in cron
    # The primary checkout is not touched: the commit is made elsewhere.
    assert (rc.root / NOTE).read_text() == "# note\n"
    assert rc.git(rc.root, "worktree", "list").count("\n") == 1


def test_a_second_run_after_a_lost_crontab_removal_does_not_append_twice(rc):
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    rc.recount("2026-10-19T12:00:00Z")
    rc.crontab_file.write_text(f"17 9 * * * recount {TAG}\n")
    out = rc.recount("2026-10-20T12:00:00Z")
    assert out.returncode == 0, out.stdout + out.stderr
    assert rc.origin_note().count("## Re-count") == 1
    assert TAG not in rc.crontab_file.read_text()


@pytest.mark.parametrize("payload", [None, {"state": "CLOSED", "closedAt": None}, "not json"])
def test_unreadable_closed_at_fails_without_appending(rc, payload):
    if payload is None:
        rc.gh_out.unlink(missing_ok=True)
    elif payload == "not json":
        rc.gh_out.write_text("not json")
    else:
        rc.gh(payload)
    out = rc.recount("2026-12-01T00:00:00Z")
    assert out.returncode != 0
    assert "closedAt" in out.stderr
    assert rc.origin_note() == "# note\n"
    assert TAG in rc.crontab_file.read_text()


def test_unreadable_crontab_is_never_rewritten(rc):
    # Only "no crontab for <user>" is an empty crontab; any other failure
    # of `crontab -l` must not install a crontab built from nothing.
    before = rc.crontab_file.read_text()
    (rc.tmp / "crontab-mode").write_text("broken")
    out = subprocess.run([sys.executable, str(SCRIPT), "install-cron"],
                         capture_output=True, text=True, env=rc.env)
    assert out.returncode != 0
    assert "cannot open spool" in out.stderr
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    out = rc.recount("2026-10-19T12:00:00Z")
    assert out.returncode != 0
    assert "cannot open spool" in out.stderr
    assert rc.crontab_file.read_text() == before


def test_install_cron_with_no_crontab_yet(rc):
    (rc.tmp / "crontab-mode").write_text("none")
    out = subprocess.run([sys.executable, str(SCRIPT), "install-cron"],
                         capture_output=True, text=True, env=rc.env)
    assert out.returncode == 0, out.stderr
    assert rc.crontab_file.read_text().count(TAG) == 1


def test_empty_window_is_an_error_not_a_result(rc):
    # Fourteen days with no transcript means the count could not see
    # them, not that nothing ran: nothing is appended, the line stays.
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    (rc.projects / "x" / "s.jsonl").unlink()
    out = rc.recount("2026-10-19T12:00:00Z")
    assert out.returncode != 0
    assert "no transcripts" in out.stderr
    assert rc.origin_note() == "# note\n"
    assert TAG in rc.crontab_file.read_text()


def test_a_failed_push_names_git_s_reason(rc):
    rc.gh({"state": "CLOSED", "closedAt": "2026-10-05T12:00:00Z"})
    hook = rc.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected by test hook' >&2\nexit 1\n")
    hook.chmod(0o755)
    out = rc.recount("2026-10-19T12:00:00Z")
    assert out.returncode != 0
    assert "rejected by test hook" in out.stderr
    assert TAG in rc.crontab_file.read_text()


def test_install_cron_adds_the_line_once(rc):
    rc.crontab_file.write_text("0 8 * * 1 other-job  # other\n")
    for _ in range(2):
        out = subprocess.run([sys.executable, str(SCRIPT), "install-cron"],
                             capture_output=True, text=True, env=rc.env)
        assert out.returncode == 0, out.stderr
    cron = rc.crontab_file.read_text()
    assert cron.count(TAG) == 1
    assert "other-job  # other" in cron
    assert "pointer_reads.py recount" in cron


def test_install_cron_from_a_worktree_names_the_primary_checkout(rc):
    # merge-cleanup deletes the worktree the install ran from, so the line
    # must name the primary checkout: here rc.root, run from a linked
    # worktree of it that holds the script.
    (rc.root / "flow" / "claude").mkdir(parents=True)
    (rc.root / "flow" / "claude" / "pointer_reads.py").write_text(SCRIPT.read_text())
    rc.git(rc.root, "add", "-A")
    rc.git(rc.root, "commit", "-q", "-m", "script")
    wt = rc.tmp / "wt"
    rc.git(rc.root, "worktree", "add", "-q", str(wt))
    rc.crontab_file.write_text("")
    out = subprocess.run([sys.executable, str(wt / "flow" / "claude" / "pointer_reads.py"), "install-cron"],
                         capture_output=True, text=True, env=rc.env)
    assert out.returncode == 0, out.stderr
    cron = rc.crontab_file.read_text()
    assert f" {rc.root.resolve()}/flow/claude/pointer_reads.py recount " in cron
    assert str(wt) not in cron

