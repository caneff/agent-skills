"""Tests for the side-channel guess/strength capture CLI (issue #296, #316)."""
import json
import os

import pytest

from assignment import STYLES
from capture import (
    _active_session,
    _resolve_session_id,
    append,
    main,
    parse_confidence_choice,
    parse_style_choice,
    record_guess,
    record_strength,
    run_guess_wizard,
    run_strength_wizard,
)

TS = "2026-08-13T12:00:00+00:00"


def test_record_guess_returns_normalized_record():
    record = record_guess("sess-1", "orwell-ste", "high", TS)
    assert record == {
        "kind": "guess",
        "session_id": "sess-1",
        "style": "orwell-ste",
        "confidence": "high",
        "turn": None,
        "ts": TS,
    }


def test_record_guess_carries_turn_number_when_given():
    record = record_guess("sess-1", "orwell-ste", "high", TS, turn=7)
    assert record["turn"] == 7


def test_record_guess_accepts_default_as_a_style():
    record = record_guess("sess-1", "default", "low", TS)
    assert record["style"] == "default"


@pytest.mark.parametrize("bad_style", ["Orwell-STE", "made-up-style", "", "ORWELL-STE"])
def test_record_guess_rejects_bad_style(bad_style):
    with pytest.raises(ValueError):
        record_guess("sess-1", bad_style, "high", TS)


@pytest.mark.parametrize("bad_confidence", ["Low", "medium", "", "1"])
def test_record_guess_rejects_bad_confidence(bad_confidence):
    with pytest.raises(ValueError):
        record_guess("sess-1", "default", bad_confidence, TS)


def test_record_guess_all_styles_accepted():
    for style in STYLES:
        assert record_guess("sess-1", style, "med", TS)["style"] == style


def test_record_strength_returns_normalized_record():
    record = record_strength("sess-1", 4, True, TS)
    assert record == {
        "kind": "strength",
        "session_id": "sess-1",
        "strength": 4,
        "faded": True,
        "ts": TS,
    }


@pytest.mark.parametrize("bad_strength", [0, 6, -1, "3"])
def test_record_strength_rejects_out_of_range(bad_strength):
    with pytest.raises(ValueError):
        record_strength("sess-1", bad_strength, False, TS)


def test_append_writes_one_jsonl_line(tmp_path):
    log_path = tmp_path / "sub" / "log.jsonl"
    record = record_guess("sess-1", "default", "low", TS)

    append(record, log_path)

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record


def test_append_is_append_only_across_calls(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append(record_guess("sess-1", "default", "low", TS), log_path)
    append(record_strength("sess-1", 3, False, TS), log_path)

    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["kind"] == "guess"
    assert json.loads(lines[1])["kind"] == "strength"


def test_strength_without_guess_is_a_valid_session(tmp_path):
    # Abstention: a session may record strength with no guess ever recorded.
    # Nothing in record_strength/append requires a prior or paired guess.
    log_path = tmp_path / "log.jsonl"
    append(record_strength("sess-abstain", 2, True, TS), log_path)

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["kind"] == "strength"
    assert record["session_id"] == "sess-abstain"


def test_main_guess_appends_record(tmp_path, monkeypatch):
    log_path = tmp_path / "log.jsonl"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-env")

    main(["guess", "plain-speak", "med", "--log-path", str(log_path)])

    record = json.loads(log_path.read_text().splitlines()[0])
    assert record["kind"] == "guess"
    assert record["session_id"] == "sess-env"
    assert record["style"] == "plain-speak"
    assert record["confidence"] == "med"
    assert "ts" in record


def test_main_strength_appends_record(tmp_path):
    log_path = tmp_path / "log.jsonl"

    main([
        "strength", "5", "yes",
        "--session-id", "sess-cli",
        "--log-path", str(log_path),
    ])

    record = json.loads(log_path.read_text().splitlines()[0])
    assert record == {
        "kind": "strength",
        "session_id": "sess-cli",
        "strength": 5,
        "faded": True,
        "ts": record["ts"],
    }


def test_main_exits_nonzero_on_bad_style(tmp_path):
    log_path = tmp_path / "log.jsonl"
    with pytest.raises(SystemExit) as excinfo:
        main(["guess", "not-a-style", "high", "--session-id", "s", "--log-path", str(log_path)])
    assert excinfo.value.code != 0
    assert not log_path.exists()


def test_main_exits_nonzero_without_session_id(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    # No detectable session either: point auto-detect at an empty turns dir.
    import stop_reminder

    monkeypatch.setattr(stop_reminder, "DEFAULT_STATE_DIR", tmp_path / "no-turns")
    log_path = tmp_path / "log.jsonl"
    with pytest.raises(SystemExit) as excinfo:
        main(["strength", "3", "no", "--log-path", str(log_path)])
    assert excinfo.value.code != 0


def test_main_guess_with_turn_records_it(tmp_path):
    log_path = tmp_path / "log.jsonl"
    main([
        "guess", "orwell-ste", "high",
        "--session-id", "s", "--log-path", str(log_path), "--turn", "12",
    ])
    record = json.loads(log_path.read_text().splitlines()[0])
    assert record["turn"] == 12


# -- gs wizard: pure input parsing -----------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("1", "clarity-and-grace"),
    ("2", "orwell-ste"),
    ("3", "plain-speak"),
    ("4", "default"),
])
def test_parse_style_choice_maps_1_to_4(raw, expected):
    assert parse_style_choice(raw) == expected


@pytest.mark.parametrize("bad", ["0", "5", "a", "", "1.5", " "])
def test_parse_style_choice_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_style_choice(bad)


@pytest.mark.parametrize("raw,expected", [
    ("l", "low"), ("L", "low"),
    ("m", "med"), ("M", "med"),
    ("h", "high"), ("H", "high"),
])
def test_parse_confidence_choice_maps_l_m_h(raw, expected):
    assert parse_confidence_choice(raw) == expected


@pytest.mark.parametrize("bad", ["low", "x", "", "1"])
def test_parse_confidence_choice_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_confidence_choice(bad)


# -- gs wizard: interactive flows -------------------------------------------


def test_run_guess_wizard_prints_style_menu(tmp_path, capsys):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["2", "h"])
    run_guess_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
        turn=9,
    )
    out = capsys.readouterr().out
    assert "Clear prose with range" in out
    assert "Clear and direct" in out
    assert "Plain-language default" in out
    assert "No injected style" in out


def test_run_guess_wizard_prints_resolved_session_id(tmp_path, capsys):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["2", "h"])
    run_guess_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
        turn=9,
    )
    out = capsys.readouterr().out
    assert "sess-w" in out


def test_run_guess_wizard_writes_record(tmp_path):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["2", "h"])
    run_guess_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
        turn=9,
    )
    record = json.loads(log_path.read_text().splitlines()[0])
    assert record == {
        "kind": "guess",
        "session_id": "sess-w",
        "style": "orwell-ste",
        "confidence": "high",
        "turn": 9,
        "ts": record["ts"],
    }


def test_run_guess_wizard_reads_turn_from_counter(tmp_path):
    turns = tmp_path / "turns"
    turns.mkdir()
    (turns / "sess-w").write_text("7 0\n")  # stop_reminder state: count last_fired
    log_path = tmp_path / "log.jsonl"
    answers = iter(["2", "h"])
    record = run_guess_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
        turn_state_dir=turns,
    )
    assert record["turn"] == 7


def test_run_guess_wizard_turn_is_none_without_counter(tmp_path):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["2", "h"])
    record = run_guess_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
        turn_state_dir=tmp_path / "empty",
    )
    assert record["turn"] is None


def test_run_guess_wizard_rejects_bad_choice_and_writes_nothing(tmp_path):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["9", "h"])
    with pytest.raises(ValueError):
        run_guess_wizard(
            input_func=lambda _prompt: next(answers),
            session_id="sess-w",
            log_path=log_path,
            turn=None,
        )
    assert not log_path.exists()


def test_run_strength_wizard_writes_record(tmp_path):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["4", "y"])
    run_strength_wizard(
        input_func=lambda _prompt: next(answers),
        session_id="sess-w",
        log_path=log_path,
    )
    record = json.loads(log_path.read_text().splitlines()[0])
    assert record["kind"] == "strength"
    assert record["strength"] == 4
    assert record["faded"] is True


def test_run_strength_wizard_rejects_bad_choice(tmp_path):
    log_path = tmp_path / "log.jsonl"
    answers = iter(["7", "y"])
    with pytest.raises(ValueError):
        run_strength_wizard(
            input_func=lambda _prompt: next(answers),
            session_id="sess-w",
            log_path=log_path,
        )
    assert not log_path.exists()


# -- active-session resolver (issue #318) ----------------------------------


def _touch(path, mtime):
    path.write_text("1 0\n")
    os.utime(path, (mtime, mtime))


def test_active_session_picks_newest_turns_file(tmp_path):
    _touch(tmp_path / "old-sess", 1000)
    _touch(tmp_path / "new-sess", 2000)
    assert _active_session(tmp_path) == "new-sess"


def test_active_session_none_when_dir_absent(tmp_path):
    assert _active_session(tmp_path / "nope") is None


def test_active_session_none_when_dir_empty(tmp_path):
    (tmp_path / "turns").mkdir()
    assert _active_session(tmp_path / "turns") is None


def test_resolve_session_id_falls_back_to_active_session(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    _touch(tmp_path / "detected-sess", 1500)
    assert _resolve_session_id(None, turns_dir=tmp_path) == "detected-sess"


def test_resolve_session_id_prefers_cli_over_detection(tmp_path):
    _touch(tmp_path / "detected-sess", 1500)
    assert _resolve_session_id("explicit", turns_dir=tmp_path) == "explicit"


def test_resolve_session_id_error_names_all_three_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    with pytest.raises(ValueError) as exc:
        _resolve_session_id(None, turns_dir=tmp_path / "empty")
    msg = str(exc.value)
    assert "--session-id" in msg
    assert "CLAUDE_CODE_SESSION_ID" in msg
    assert "hook" in msg or "reminder" in msg
