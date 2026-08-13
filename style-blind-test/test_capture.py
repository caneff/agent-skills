"""Tests for the side-channel guess/strength capture CLI (issue #296)."""
import json

import pytest

from assignment import STYLES
from capture import append, main, record_guess, record_strength

TS = "2026-08-13T12:00:00+00:00"


def test_record_guess_returns_normalized_record():
    record = record_guess("sess-1", "orwell-ste", "high", TS)
    assert record == {
        "kind": "guess",
        "session_id": "sess-1",
        "style": "orwell-ste",
        "confidence": "high",
        "ts": TS,
    }


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
        record_guess("sess-1", style, "med", TS)


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
    log_path = tmp_path / "log.jsonl"
    with pytest.raises(SystemExit) as excinfo:
        main(["strength", "3", "no", "--log-path", str(log_path)])
    assert excinfo.value.code != 0
