"""Tests for the batch-reveal scorer (issue #298)."""
import json

import pytest

from assignment import assignment
from score import build_records, count_assistant_turns, main, tally


def _rec(session_id, truth, hook_on, guess=None, confidence=None,
         strength=None, faded=None, turns=0):
    return {
        "session_id": session_id,
        "truth": truth,
        "hook_on": hook_on,
        "guess": guess,
        "confidence": confidence,
        "strength": strength,
        "faded": faded,
        "turns": turns,
    }


def test_tally_raw_hit_rate_and_baseline():
    records = [
        _rec("s1", "orwell-ste", True, guess="orwell-ste", confidence="high"),
        _rec("s2", "plain-speak", True, guess="orwell-ste", confidence="high"),
    ]
    stats = tally(records)
    assert stats["n_guesses"] == 2
    assert stats["raw_hit_rate"] == pytest.approx(0.5)
    assert stats["raw_baseline"] == 0.25


def test_tally_nondefault_conditioned_hit_rate():
    records = [
        _rec("s1", "default", True, guess="default", confidence="high"),
        _rec("s2", "orwell-ste", True, guess="orwell-ste", confidence="high"),
        _rec("s3", "plain-speak", True, guess="orwell-ste", confidence="high"),
    ]
    stats = tally(records)
    # raw: 2/3 correct; nondefault: 1/2 correct (s1 excluded from denominator)
    assert stats["raw_hit_rate"] == pytest.approx(2 / 3)
    assert stats["nondefault_hit_rate"] == pytest.approx(0.5)


def test_tally_by_confidence_breakdown():
    records = [
        _rec("s1", "orwell-ste", True, guess="orwell-ste", confidence="low"),
        _rec("s2", "plain-speak", True, guess="orwell-ste", confidence="low"),
        _rec("s3", "orwell-ste", True, guess="orwell-ste", confidence="high"),
    ]
    stats = tally(records)
    assert stats["by_confidence"]["low"] == pytest.approx(0.5)
    assert stats["by_confidence"]["high"] == pytest.approx(1.0)
    assert stats["by_confidence"]["med"] is None


def test_tally_turn_gate_splits_hook_on_off_strength():
    records = [
        _rec("s1", "orwell-ste", True, strength=4, turns=30),
        _rec("s2", "orwell-ste", True, strength=2, turns=5),  # below gate
        _rec("s3", "orwell-ste", False, strength=1, turns=15),  # in 10-24 band
        _rec("s4", "orwell-ste", False, strength=3, turns=40),
    ]
    stats = tally(records)
    assert stats["n_qualifying"] == 3  # s1, s3, s4 (turns >= 10)
    assert stats["hook_on_mean_strength"] == pytest.approx(4.0)
    assert stats["hook_off_mean_strength"] == pytest.approx(2.0)


def test_tally_all_abstention_does_not_crash():
    records = [
        _rec("s1", "orwell-ste", True, guess=None, turns=20),
        _rec("s2", "plain-speak", False, guess=None, turns=20),
    ]
    stats = tally(records)
    assert stats["n_guesses"] == 0
    assert stats["raw_hit_rate"] is None
    assert stats["nondefault_hit_rate"] is None
    assert stats["by_confidence"] == {"low": None, "med": None, "high": None}


def test_tally_zero_qualifying_sessions_does_not_crash():
    records = [
        _rec("s1", "orwell-ste", True, guess="orwell-ste", confidence="high",
             strength=4, turns=3),
        _rec("s2", "orwell-ste", False, guess="orwell-ste", confidence="high",
             strength=2, turns=1),
    ]
    stats = tally(records)
    assert stats["n_qualifying"] == 0
    assert stats["hook_on_mean_strength"] is None
    assert stats["hook_off_mean_strength"] is None
    # hit-rate is unaffected by the turn gate
    assert stats["raw_hit_rate"] == pytest.approx(1.0)


def test_tally_all_default_truths_does_not_crash():
    records = [
        _rec("s1", "default", True, guess="default", confidence="high"),
        _rec("s2", "default", False, guess="orwell-ste", confidence="low"),
    ]
    stats = tally(records)
    assert stats["nondefault_hit_rate"] is None
    assert stats["raw_hit_rate"] == pytest.approx(0.5)


def test_count_assistant_turns_counts_only_assistant_lines(tmp_path):
    proj = tmp_path / "myproject"
    proj.mkdir()
    transcript = proj / "sess-1.jsonl"
    lines = [
        {"type": "assistant", "sessionId": "sess-1"},
        {"type": "user", "sessionId": "sess-1"},
        {"type": "assistant", "sessionId": "sess-1"},
        {"type": "attachment", "sessionId": "sess-1"},
        {"type": "assistant", "sessionId": "sess-1"},
    ]
    transcript.write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    assert count_assistant_turns("sess-1", projects_dir=tmp_path) == 3


def test_count_assistant_turns_excludes_subagents_dir(tmp_path):
    # A "subagents" directory sits at the same depth the glob
    # (projects_dir/*/<session_id>.jsonl) reaches -- it must be filtered out
    # by name, not merely missed by depth. No other transcript exists, so a
    # buggy implementation that fails to exclude it would return 10, not 0.
    sub_dir = tmp_path / "subagents"
    sub_dir.mkdir()
    (sub_dir / "sess-2.jsonl").write_text(
        "\n".join(
            json.dumps({"type": "assistant", "sessionId": "sess-2"})
            for _ in range(10)
        )
        + "\n"
    )

    assert count_assistant_turns("sess-2", projects_dir=tmp_path) == 0


def test_count_assistant_turns_finds_real_transcript_ignoring_subagents_sibling(tmp_path):
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "sess-3.jsonl").write_text(
        json.dumps({"type": "assistant", "sessionId": "sess-3"}) + "\n"
    )
    sub_dir = tmp_path / "subagents"
    sub_dir.mkdir()
    (sub_dir / "sess-3.jsonl").write_text(
        "\n".join(
            json.dumps({"type": "assistant", "sessionId": "sess-3"})
            for _ in range(10)
        )
        + "\n"
    )

    assert count_assistant_turns("sess-3", projects_dir=tmp_path) == 1


def test_count_assistant_turns_missing_transcript_returns_zero(tmp_path):
    assert count_assistant_turns("no-such-session", projects_dir=tmp_path) == 0


def _write_log(log_path, lines):
    with open(log_path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def test_build_records_emits_one_record_per_guess_line(tmp_path):
    log_path = tmp_path / "log.jsonl"
    projects_dir = tmp_path / "projects"
    session_id = "multi-guess"
    truth, _hook_on = assignment(session_id)

    _write_log(log_path, [
        {"kind": "guess", "session_id": session_id, "style": truth,
         "confidence": "low", "turn": 5, "ts": "t"},
        {"kind": "guess", "session_id": session_id, "style": truth,
         "confidence": "high", "turn": 30, "ts": "t"},
    ])

    records = build_records(log_path, projects_dir)
    assert len(records) == 2
    turns_logged = sorted(r["turn"] for r in records)
    assert turns_logged == [5, 30]
    assert all(r["session_id"] == session_id for r in records)
    assert all(r["guess"] == truth for r in records)


def test_build_records_every_guess_counts_as_a_trial_in_tally(tmp_path):
    log_path = tmp_path / "log.jsonl"
    projects_dir = tmp_path / "projects"
    session_id = "multi-guess-2"
    truth, _hook_on = assignment(session_id)
    wrong = next(s for s in ("clarity-and-grace", "orwell-ste", "plain-speak", "default")
                 if s != truth)

    _write_log(log_path, [
        {"kind": "guess", "session_id": session_id, "style": truth,
         "confidence": "low", "turn": 5, "ts": "t"},
        {"kind": "guess", "session_id": session_id, "style": wrong,
         "confidence": "high", "turn": 30, "ts": "t"},
    ])

    stats = tally(build_records(log_path, projects_dir))
    assert stats["n_guesses"] == 2
    assert stats["raw_hit_rate"] == pytest.approx(0.5)


def test_build_records_abstention_session_still_yields_one_record(tmp_path):
    log_path = tmp_path / "log.jsonl"
    projects_dir = tmp_path / "projects"
    session_id = "abstain-only"

    _write_log(log_path, [
        {"kind": "strength", "session_id": session_id, "strength": 3,
         "faded": False, "ts": "t"},
    ])

    records = build_records(log_path, projects_dir)
    assert len(records) == 1
    assert records[0]["guess"] is None
    assert records[0]["strength"] == 3


def test_score_main_smoke(tmp_path, capsys):
    log_path = tmp_path / "log.jsonl"
    projects_dir = tmp_path / "projects"
    proj = projects_dir / "myproject"
    proj.mkdir(parents=True)

    session_id = "smoke-session"
    truth, hook_on = assignment(session_id)

    with open(log_path, "w") as f:
        f.write(json.dumps({
            "kind": "guess", "session_id": session_id, "style": truth,
            "confidence": "high", "ts": "2026-08-13T00:00:00+00:00",
        }) + "\n")
        f.write(json.dumps({
            "kind": "strength", "session_id": session_id, "strength": 3,
            "faded": False, "ts": "2026-08-13T00:00:00+00:00",
        }) + "\n")

    with open(proj / f"{session_id}.jsonl", "w") as f:
        for _ in range(16):
            f.write(json.dumps({"type": "assistant", "sessionId": session_id}) + "\n")

    main(["--log-path", str(log_path), "--projects-dir", str(projects_dir)])

    out = capsys.readouterr().out
    assert "n_guesses" in out or "guesses" in out.lower()
