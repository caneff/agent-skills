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
            _first_user("2026-01-01T00:00:05.000Z"),
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


def test_pr_open_ignores_the_phrase_quoted_inside_another_command():
    """#826 correctness finding C1: a Bash call that merely mentions the
    literal phrase — e.g. this tool inspecting its own past transcripts —
    is not a real `gh pr create` invocation and must not be matched."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:05:00.000Z",
                       ("b0", "Bash", {"command":
                        'python3 -c "if \'gh pr create\' in cmd: print(1)"'})),
            _assistant("2026-01-01T00:30:00.000Z",
                       ("b1", "Bash", {"command": "gh pr create --title x"})),
            _result("2026-01-01T00:30:02.000Z", "b1"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["pr_open"]
        assert start == "2026-01-01T00:30:00.000Z", start
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


def test_report_ignores_the_phrase_mentioned_mid_message():
    """A planning message that merely discusses "PR up" ('before PR up has
    no Seams...') is not the worker's actual report — the implement skill's
    convention is that the report always *starts* with "PR up"."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:20:00.000Z",
                       ("m0", "SendMessage", {"to": "controller",
                        "message": "#9 (check X before PR up) has no seams. Plan: ..."})),
            _assistant("2026-01-01T00:31:00.000Z",
                       ("m1", "SendMessage", {"to": "controller",
                                               "message": "PR up for #9: url"})),
            _result("2026-01-01T00:31:01.000Z", "m1"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        start, duration = lines["report"]
        assert start == "2026-01-01T00:31:00.000Z", start
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


def test_a_non_string_or_malformed_timestamp_is_skipped_not_fatal():
    """#826 correctness findings C2/C3: a numeric timestamp used to raise
    TypeError on sort, and a malformed string raised ValueError on parse —
    both should be tolerated like a half-written JSON line, not kill the
    whole run (the module's own docstring promises exactly that)."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            json.dumps({"type": "user", "timestamp": 12345, "message": {"content": "x"}}),
            json.dumps({"type": "user", "timestamp": "bogus",
                        "message": {"content": "x"}}),
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        r = _run(tmp, WORKTREE)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = _lines(r.stdout, WORKTREE)
        assert lines["dispatch"] == ("2026-01-01T00:00:00.000Z", "-")


def test_a_subagents_edit_call_does_not_count_as_the_workers_build():
    """A subagent's own transcript lives one level down, under
    `<session>/subagents/`, and is a different agent's work entirely — an
    Edit call in there must not be read as the worker's first edit."""
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:10:00.000Z", ("t1", "Edit", {})),
        ])
        subagent_dir = os.path.join(project, "s", "subagents")
        os.makedirs(subagent_dir, exist_ok=True)
        with open(os.path.join(subagent_dir, "agent-x.jsonl"), "w") as f:
            f.write(_assistant("2026-01-01T00:01:00.000Z", ("t0", "Edit", {})) + "\n")
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert lines["build"] == ("2026-01-01T00:10:00.000Z", "-")


def test_multiple_session_files_merge_in_timestamp_order_not_filename_order():
    """#826 correctness finding H4: a resumed session writes a second
    session-id jsonl file that can sort after the first one by filename
    while its entries are chronologically first. Filename order is the
    reverse of time order here, so a fixture where they happen to agree
    (verification-pass finding, first fixture) can't witness the sort."""
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "a-alphabetically-first.jsonl"), [
            _first_user("2026-01-01T00:05:00.000Z"),
        ])
        _write(os.path.join(project, "z-alphabetically-last.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert lines["dispatch"] == ("2026-01-01T00:00:00.000Z", "-")


def test_timestamps_sort_by_parsed_time_not_string_order():
    """#826 correctness finding C4: a non-UTC offset sorts wrong as a raw
    string. `...T00:00:00.500+01:00` (= 2025-12-31T23:00:00.500Z, earlier)
    raw-string-sorts *after* `...T00:00:00.000Z` (2026-01-01T00:00:00.000Z,
    later) — '5' > '0' at the first differing character — even though it
    names the chronologically earlier instant."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _first_user("2026-01-01T00:00:00.500+01:00"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert lines["dispatch"] == ("2026-01-01T00:00:00.500+01:00", "-")


def test_ambiguous_ticket_number_disambiguates_its_identifier():
    """#826 correctness finding C6: two repos can each have their own
    implement-<n> worktree for the same ticket number; the two rows must
    not collide under one identifier with no way to tell them apart."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "-home-a-repo--claude-worktrees-implement-9", "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        _write(os.path.join(tmp, "-home-b-repo--claude-worktrees-implement-9", "s.jsonl"), [
            _first_user("2026-01-02T00:00:00.000Z"),
        ])
        r = _run(tmp, "9")
        assert r.returncode == 0, r.stdout + r.stderr
        dispatches = sorted(l.split(" ", 3)[2] for l in r.stdout.splitlines()
                             if l.split(" ", 3)[1] == "dispatch")
        assert dispatches == ["2026-01-01T00:00:00.000Z", "2026-01-02T00:00:00.000Z"]
        idents = {l.split(" ", 1)[0] for l in r.stdout.splitlines()}
        assert len(idents) == 2, idents


def test_a_tool_result_mentioning_the_phrase_is_not_an_incoming_message():
    """#826 correctness finding C7: the incoming-message detector substring-
    matches serialized tool_result content too, so a review or a doc that
    merely discusses "cross-session-message" would be misread as a reply
    and close a pending wait early."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:40:00.000Z",
                       ("m1", "SendMessage", {"to": "controller", "message": "merge?"})),
            _result("2026-01-01T00:40:05.000Z", "m1"),
            json.dumps({"type": "user", "timestamp": "2026-01-01T00:41:00.000Z", "message": {
                "content": [{"type": "tool_result", "tool_use_id": "b1", "content": [
                    {"type": "text", "text": "docs mention cross-session-message here"}]}]}}),
            _incoming("2026-01-01T00:43:00.000Z"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert float(lines["waiting_on_controller"][1]) == 180.0  # 00:40 -> 00:43, not 00:41


def test_two_outgoing_messages_before_one_reply_count_the_wait_once():
    """#826 correctness finding H3: the alternating OUT/IN fixture never
    witnessed the `if pending is None` guard — two sends before a single
    reply must not double the wait, and it's measured from the first send."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
            _assistant("2026-01-01T00:40:00.000Z",
                       ("m1", "SendMessage", {"to": "controller", "message": "merge?"})),
            _assistant("2026-01-01T00:41:00.000Z",
                       ("m2", "SendMessage", {"to": "controller", "message": "still there?"})),
            _incoming("2026-01-01T00:43:00.000Z"),
        ])
        r = _run(tmp, WORKTREE)
        lines = _lines(r.stdout, WORKTREE)
        assert float(lines["waiting_on_controller"][1]) == 180.0  # 00:40 -> 00:43, once


def test_piped_output_exits_clean_on_a_closed_reader():
    """#826 correctness finding C9: with enough output in flight that the
    writer is still mid-`print` when the reader goes away, the old
    substring-matched code raised BrokenPipeError to a bare traceback. A
    single worktree's ~7 lines fit inside the OS pipe buffer and the
    process exits before a reader can even close it, so this needs enough
    volume (many repeated args, passed as a real argv list to dodge the
    shell's argument-length limit) to force the write to block past the
    close — a `sleep`-based race would be flaky instead."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        proc = subprocess.Popen(
            [sys.executable, PHASES, *([WORKTREE] * 2000)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "BURNDOWN_PROJECTS_DIR": tmp},
        )
        proc.stdout.read(1024)
        proc.stdout.close()
        _, stderr = proc.communicate(timeout=5)
        assert "Traceback" not in stderr, stderr
        assert "BrokenPipeError" not in stderr, stderr


def test_a_ticket_number_resolves_to_its_matching_project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "s.jsonl"), [
            _first_user("2026-01-01T00:00:00.000Z"),
        ])
        r = _run(tmp, "9")
        assert r.returncode == 0, r.stdout + r.stderr
        lines = _lines(r.stdout, "9")
        assert lines["dispatch"] == ("2026-01-01T00:00:00.000Z", "-")


def test_an_unmatched_ticket_number_warns_on_stderr_but_still_prints_dashes():
    """A dash-filled row alone (the format every other case prints) would
    be indistinguishable from a real worktree whose transcript is simply
    missing — the stderr line is what tells the two apart."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(tmp, "404")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "404" in r.stderr
        lines = _lines(r.stdout, "404")
        assert lines["dispatch"] == ("-", "-")


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
