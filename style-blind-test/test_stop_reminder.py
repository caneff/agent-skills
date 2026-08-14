"""Tests for the Stop-event reminder hook (issue #316)."""
import json

import stop_reminder
from stop_reminder import (
    REMINDER_MESSAGE,
    run,
    should_fire,
)


def test_should_fire_on_exact_threshold():
    assert should_fire(24, 25, interval=25) is True


def test_should_fire_false_below_threshold():
    assert should_fire(10, 24, interval=25) is False


def test_should_fire_true_when_a_threshold_is_crossed_by_a_jump():
    # counter can jump by more than 1 between reads in principle -- any
    # crossing of a multiple-of-interval boundary should fire.
    assert should_fire(23, 27, interval=25) is True


def test_should_fire_false_when_already_past_and_not_crossing_new_one():
    assert should_fire(26, 27, interval=25) is False


def test_should_fire_at_second_threshold():
    assert should_fire(49, 50, interval=25) is True


def test_should_fire_false_at_zero():
    assert should_fire(0, 0, interval=25) is False


def test_should_fire_false_for_count_zero_to_one():
    assert should_fire(0, 1, interval=25) is False


def test_run_increments_counter_file_and_fires_at_threshold(tmp_path):
    state_dir = tmp_path / "turns"
    session_id = "sess-1"

    fired = []
    for _ in range(9):
        fired.append(run(json.dumps({"session_id": session_id}), state_dir=state_dir))
    assert all(f is False for f in fired)

    result = run(json.dumps({"session_id": session_id}), state_dir=state_dir)
    assert result is True

    count_file = state_dir / session_id
    assert count_file.read_text().split()[0] == "10"


def test_run_does_not_refire_same_threshold_on_repeat(tmp_path):
    state_dir = tmp_path / "turns"
    session_id = "sess-2"
    # drive straight to the file having last_fired=10, count=10
    (state_dir).mkdir(parents=True)
    (state_dir / session_id).write_text("10 10")

    result = run(json.dumps({"session_id": session_id}), state_dir=state_dir)
    # next call increments to 11, no new threshold crossed
    assert result is False


def test_run_tracks_sessions_independently(tmp_path):
    state_dir = tmp_path / "turns"
    run(json.dumps({"session_id": "a"}), state_dir=state_dir)
    result = run(json.dumps({"session_id": "b"}), state_dir=state_dir)
    assert result is False
    assert (state_dir / "a").read_text().strip().split()[0] == "1"
    assert (state_dir / "b").read_text().strip().split()[0] == "1"


def test_run_notifies_with_the_firing_session_id_and_cwd(tmp_path, monkeypatch):
    state_dir = tmp_path / "turns"
    session_id = "sess-notify"
    calls = []
    monkeypatch.setattr(
        stop_reminder, "_notify", lambda sid, cwd=None: calls.append((sid, cwd))
    )

    for _ in range(9):
        run(json.dumps({"session_id": session_id, "cwd": "/x/proj"}), state_dir=state_dir)
    run(json.dumps({"session_id": session_id, "cwd": "/x/proj"}), state_dir=state_dir)

    assert calls == [(session_id, "/x/proj")]


def test_run_notifies_with_no_cwd_when_absent(tmp_path, monkeypatch):
    state_dir = tmp_path / "turns"
    session_id = "sess-nocwd"
    calls = []
    monkeypatch.setattr(
        stop_reminder, "_notify", lambda sid, cwd=None: calls.append((sid, cwd))
    )

    for _ in range(9):
        run(json.dumps({"session_id": session_id}), state_dir=state_dir)
    run(json.dumps({"session_id": session_id}), state_dir=state_dir)

    assert calls == [(session_id, None)]


def test_notify_toast_is_long_loud_and_shows_project_and_short_id(monkeypatch):
    import shutil

    calls = []

    class FakeResult:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "wslpath":
            return FakeResult(0, "C:\\fake\\toast.ps1\n")
        return FakeResult(0, "")

    monkeypatch.setattr(shutil, "which", lambda name: "/fake/powershell.exe")
    monkeypatch.setattr(stop_reminder.subprocess, "run", fake_run)

    stop_reminder._notify("sess-0123456789", cwd="/home/x/my-proj")

    toast_call = calls[-1]
    assert "-Duration" in toast_call
    assert toast_call[toast_call.index("-Duration") + 1] == "long"
    body = toast_call[toast_call.index("-Body") + 1]
    assert "my-proj" in body
    assert "sess-012" in body


def test_reminder_message_reveals_no_style():
    for style in ("clarity-and-grace", "orwell-ste", "plain-speak", "default"):
        assert style not in REMINDER_MESSAGE
    assert "gs" in REMINDER_MESSAGE
