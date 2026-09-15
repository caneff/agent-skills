#!/usr/bin/env python3
"""Tests for the phase-timing reporter (#826). Seam: a worktree path or
ticket number in, `<identifier> <phase> <start> <duration>` lines out, over
a synthetic projects dir — same convention as cost_test.py."""
import json
import os
import subprocess
import sys
import tempfile

PHASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phases.py")
WORKTREE = "/home/someone/repo/.claude/worktrees/implement-9"
PROJECT_DIR = "-home-someone-repo--claude-worktrees-implement-9"


def _assistant(ts, *tool_uses):
    content = [{"type": "tool_use", "id": tid, "name": name, "input": inp}
               for tid, name, inp in tool_uses]
    return json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"content": content}})


def _result(ts, tool_use_id):
    return json.dumps({"type": "user", "timestamp": ts, "message": {
        "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                     "content": [{"type": "text", "text": "ok"}]}]}})


def _subagent(project_root, session, agent_id, tool_use_id, description, last_ts):
    """A finished background Agent spawn: `<session>/subagents/agent-<id>`
    `.meta.json` (carrying the `toolUseId` that links back to the mainline
    Agent tool_use) plus its `.jsonl` transcript, whose last entry's
    timestamp is the real completion time — the mainline `tool_result` on
    an Agent call only marks the async launch, not the finish."""
    base = os.path.join(project_root, session, "subagents", f"agent-{agent_id}")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + ".meta.json", "w") as f:
        json.dump({"agentType": "diff-reviewer", "description": description,
                    "toolUseId": tool_use_id}, f)
    with open(base + ".jsonl", "w") as f:
        f.write(json.dumps({"type": "assistant", "timestamp": last_ts,
                             "isSidechain": True}) + "\n")


def _incoming(ts, frm="controller"):
    return json.dumps({"type": "user", "timestamp": ts, "message": {
        "content": f'Another Claude session sent a message:\n'
                    f'<cross-session-message from="{frm}">hi</cross-session-message>'}})


def _first_user(ts):
    return json.dumps({"type": "user", "timestamp": ts,
                        "message": {"content": "/implement 9 --tier heavy"}})


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("".join(line + "\n" for line in lines))


def _run(root, *args):
    return subprocess.run(
        [sys.executable, PHASES, *args], capture_output=True, text=True,
        env={**os.environ, "BURNDOWN_PROJECTS_DIR": root},
    )


def _lines(stdout, identifier):
    out = {}
    for line in stdout.splitlines():
        ident, phase, start, duration = line.split(" ", 3)
        if ident == identifier:
            out[phase] = (start, duration)
    return out


def test_dispatch_is_the_first_entrys_timestamp_with_no_duration():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        r = _run(tmp, WORKTREE)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = _lines(r.stdout, WORKTREE)
        assert lines["dispatch"] == ("2026-01-01T00:00:00.000Z", "-")


def test_build_starts_at_the_first_edit_or_write():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:01:00.000Z", ("t1", "Read", {})),
            _assistant("2026-01-01T00:02:00.000Z", ("t2", "Edit", {})),
            _assistant("2026-01-01T00:03:00.000Z", ("t3", "Write", {})),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert lines["build"] == ("2026-01-01T00:02:00.000Z", "-")


def test_review_round_1_spans_the_axis_skill_call_to_its_last_agent_result():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:10:00.000Z",
                       ("skill1", "Skill", {"skill": "multi-axis-code-review"})),
            _assistant("2026-01-01T00:10:05.000Z",
                       ("a1", "Agent", {"subagent_type": "diff-reviewer",
                                        "description": "Standards axis review"})),
            _assistant("2026-01-01T00:10:10.000Z",
                       ("a2", "Agent", {"subagent_type": "diff-reviewer",
                                        "description": "Spec axis review"})),
            _result("2026-01-01T00:10:06.000Z", "a1"),  # async-launch ack, not the finish
            _result("2026-01-01T00:10:11.000Z", "a2"),
        ])
        _subagent(project, "s", "1", "a1", "Standards axis review", "2026-01-01T00:12:00.000Z")
        _subagent(project, "s", "2", "a2", "Spec axis review", "2026-01-01T00:15:00.000Z")
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["review_round_1"]
        assert start == "2026-01-01T00:10:00.000Z"
        assert float(duration) == 300.0  # 00:10:00 -> 00:15:00 (last subagent finish)


def test_verification_is_the_agent_call_whose_prompt_says_verify():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:20:00.000Z",
                       ("a3", "Agent", {"subagent_type": "diff-reviewer",
                                        "description": "Verify round-1 fixes"})),
            _result("2026-01-01T00:20:01.000Z", "a3"),  # async-launch ack, not the finish
        ])
        _subagent(project, "s", "3", "a3", "Verify round-1 fixes", "2026-01-01T00:25:00.000Z")
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["verification"]
        assert start == "2026-01-01T00:20:00.000Z"
        assert float(duration) == 300.0


def test_pr_open_is_the_gh_pr_create_bash_call():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:30:00.000Z",
                       ("b1", "Bash", {"command": "gh pr create --title x"})),
            _result("2026-01-01T00:30:02.000Z", "b1"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["pr_open"]
        assert start == "2026-01-01T00:30:00.000Z"
        assert float(duration) == 2.0


def test_report_is_the_sendmessage_mentioning_pr_up():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:31:00.000Z",
                       ("m1", "SendMessage", {"to": "controller",
                                               "message": "PR up for #9: url"})),
            _result("2026-01-01T00:31:01.000Z", "m1"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["report"]
        assert start == "2026-01-01T00:31:00.000Z"
        assert float(duration) == 1.0


def test_waiting_on_controller_sums_gaps_from_each_outgoing_to_the_next_incoming():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:40:00.000Z",
                       ("m1", "SendMessage", {"to": "controller", "message": "merge?"})),
            _incoming("2026-01-01T00:43:00.000Z"),  # 180s wait
            _assistant("2026-01-01T00:50:00.000Z",
                       ("m2", "SendMessage", {"to": "controller", "message": "again?"})),
            _incoming("2026-01-01T00:51:30.000Z"),  # 90s wait
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert float(lines["waiting_on_controller"][1]) == 270.0


def test_a_ticket_number_resolves_to_its_matching_project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        r = _run(tmp, "9")
        assert r.returncode == 0, r.stdout + r.stderr
        lines = _lines(r.stdout, "9")
        assert lines["dispatch"] == ("2026-01-01T00:00:00.000Z", "-")


def test_a_missing_transcript_prints_dashes_and_does_not_die():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(tmp, "/home/nobody/never/built")
        assert r.returncode == 0, r.stdout + r.stderr
        lines = _lines(r.stdout, "/home/nobody/never/built")
        assert lines["dispatch"] == ("-", "-")
        assert lines["waiting_on_controller"] == ("-", "0.0")


def test_the_script_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        before = sorted(
            (os.path.join(d, f), os.path.getsize(os.path.join(d, f)))
            for d, _, files in os.walk(tmp) for f in files)
        assert _run(tmp, WORKTREE).returncode == 0
        after = sorted(
            (os.path.join(d, f), os.path.getsize(os.path.join(d, f)))
            for d, _, files in os.walk(tmp) for f in files)
        assert before == after, "the script must only read"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
