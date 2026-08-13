"""Tests for the session-hashed style assignment core (issue #295)."""
from assignment import STYLES, assignment

IDS = [f"session-{i}" for i in range(200)]


def test_assignment_returns_style_and_hook_on():
    style, hook_on = assignment("session-abc")
    assert style in STYLES
    assert isinstance(hook_on, bool)


def test_assignment_deterministic_for_same_id():
    first = assignment("session-abc")
    second = assignment("session-abc")
    assert first == second


def test_all_styles_and_both_hook_states_appear_across_spread_of_ids():
    results = [assignment(sid) for sid in IDS]
    styles_seen = {style for style, _ in results}
    hook_states_seen = {hook_on for _, hook_on in results}
    assert styles_seen == set(STYLES)
    assert hook_states_seen == {True, False}


def test_style_and_hook_on_are_independent():
    # For each style that appears, both hook_on states should also appear
    # within it -- if hook_on were derived from style (or the same salt),
    # it would collapse to a single value per style.
    by_style: dict[str, set[bool]] = {}
    for sid in IDS:
        style, hook_on = assignment(sid)
        by_style.setdefault(style, set()).add(hook_on)
    for style, hook_states in by_style.items():
        assert hook_states == {True, False}, (
            f"style {style!r} only ever saw hook_on={hook_states}, "
            "suggesting hook_on is not independently derived"
        )


def test_assignment_stable_across_hook_source():
    # assignment() takes only session_id -- source is never a parameter,
    # so calling it with the same id is inherently source-independent.
    # This test documents that guarantee explicitly.
    session_id = "session-stable"
    results = {assignment(session_id) for _ in ("startup", "clear", "resume", "compact")}
    assert len(results) == 1
