#!/usr/bin/env python3
"""Tests for the burn cost script (#631). Seam: a worktree path in, three
integers out, over a synthetic projects dir — `BURNDOWN_PROJECTS_DIR` keeps
every case off the real `~/.claude/projects`."""
import json
import os
import subprocess
import sys
import tempfile

COST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cost.py")
WORKTREE = "/home/someone/orca/workspaces/repo/a"
PROJECT_DIR = "-home-someone-orca-workspaces-repo-a"


def _line(sidechain, *, inp=0, cache_creation=0, cache_read=0, out=0, mid=None):
    return json.dumps({
        "isSidechain": sidechain,
        "uuid": mid or f"uuid-{inp}-{out}-{sidechain}",
        "message": {"id": mid, "usage": {
            "input_tokens": inp,
            "cache_creation_input_tokens": cache_creation,
            "cache_read_input_tokens": cache_read,
            "output_tokens": out,
            "cache_creation": {"ephemeral_5m_input_tokens": cache_creation},
            "output_tokens_details": {"thinking_tokens": out},
        }},
    })


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("".join(line + "\n" for line in lines))


def _run(root, worktree=WORKTREE):
    return subprocess.run(
        [sys.executable, COST, worktree], capture_output=True, text=True,
        env={**os.environ, "BURNDOWN_PROJECTS_DIR": root},
    )


def _snapshot(root):
    return sorted(
        (os.path.join(d, f), os.path.getsize(os.path.join(d, f)))
        for d, _, files in os.walk(root) for f in files
    )


def test_main_lines_count_as_builder_and_sidechain_lines_as_review():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "session.jsonl"), [
            _line(False, inp=10, cache_creation=100, cache_read=1000, out=1),
            json.dumps({"type": "summary", "summary": "no usage here"}),
            _line(False, inp=5),
        ])
        _write(os.path.join(project, "session", "subagents", "agent-a.jsonl"), [
            _line(True, inp=2, out=20),
        ])
        r = _run(tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout == "1116 22 1138\n", r.stdout


def test_no_sidechain_lines_prints_zero_review():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "session.jsonl"),
               [_line(False, inp=7, out=3)])
        r = _run(tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout == "10 0 10\n", r.stdout


def test_a_missing_projects_dir_prints_zeros_and_exits_clean():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(tmp, worktree="/home/someone/never/built/here")
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout == "0 0 0\n", r.stdout


def test_the_script_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "session.jsonl"),
               [_line(False, inp=7), _line(True, out=3)])
        before = _snapshot(tmp)
        assert _run(tmp).returncode == 0
        assert _snapshot(tmp) == before, "the script must only read"


def test_a_dotted_path_segment_doubles_the_hyphen():
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "-home-someone--agents-skills", "s.jsonl"),
               [_line(False, inp=4)])
        r = _run(tmp, worktree="/home/someone/.agents/skills")
        assert r.stdout == "4 0 4\n", r.stdout


def test_one_message_split_over_several_lines_counts_once():
    """Claude writes one assistant message as one JSONL entry per content
    block — thinking, text, each tool call — all carrying the same usage."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, PROJECT_DIR, "session.jsonl"), [
            _line(False, inp=6, out=1, mid="msg_1"),
            _line(False, inp=6, out=1, mid="msg_1"),
            _line(False, inp=6, out=1, mid="msg_1"),
            _line(False, inp=2, out=0, mid="msg_2"),
        ])
        r = _run(tmp)
        assert r.stdout == "9 0 9\n", r.stdout


def test_junk_in_the_transcript_dir_never_kills_the_tally():
    """Settle time is the wrong place to die: a half-written line, a bare JSON
    scalar, and the `.meta.json` siblings Claude writes beside every subagent
    transcript all have to pass through."""
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, PROJECT_DIR)
        _write(os.path.join(project, "session.jsonl"), [
            _line(False, inp=8),
            '{"message": {"usage": {"input_tokens": 99',  # truncated mid-write
            "null",
            "[1, 2, 3]",
        ])
        _write(os.path.join(project, "session", "subagents", "agent-a.meta.json"),
               [json.dumps({"message": {"usage": {"input_tokens": 4000}}})])
        r = _run(tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout == "8 0 8\n", r.stdout


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
