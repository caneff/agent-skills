"""Tests for the UserPromptSubmit hook entrypoint (issue #297)."""
import json

from assignment import assignment
from user_prompt_submit import run

FIXTURES = {
    "clarity-and-grace": ("Clarity and Grace", "---\nname: Clarity and Grace\n---\nbody\n"),
    "orwell-ste": ("Orwell STE", "---\nname: Orwell STE\n---\nbody\n"),
    "plain-speak": ("Plain Speak", "---\nname: Plain Speak\n---\nbody\n"),
}


def _make_styles_dir(tmp_path):
    styles_dir = tmp_path / "output-styles"
    styles_dir.mkdir()
    for style, (_name, body) in FIXTURES.items():
        (styles_dir / f"{style}.md").write_text(body)
    return styles_dir


def _find_session_id_for(target_style, target_hook_on):
    for i in range(2000):
        sid = f"session-{i}"
        style, hook_on = assignment(sid)
        if style == target_style and hook_on == target_hook_on:
            return sid
    raise AssertionError(
        f"no session id in range produced style={target_style!r} hook_on={target_hook_on!r}"
    )


def test_hook_on_true_non_default_emits_reminder_with_style_name(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for("clarity-and-grace", True)
    hook_input = json.dumps({"session_id": session_id})

    output = run(hook_input, styles_dir=styles_dir)

    parsed = json.loads(output)
    assert parsed == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "Output style: Clarity and Grace. "
                "Stay in that voice; self-check before sending."
            ),
        }
    }


def test_hook_on_false_emits_nothing(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for("clarity-and-grace", False)
    hook_input = json.dumps({"session_id": session_id})

    output = run(hook_input, styles_dir=styles_dir)

    assert output == ""


def test_default_style_emits_nothing_even_when_hook_on(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for("default", True)
    hook_input = json.dumps({"session_id": session_id})

    output = run(hook_input, styles_dir=styles_dir)

    assert output == ""


def test_reminder_name_matches_assignment_choice(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for("orwell-ste", True)
    style, _hook_on = assignment(session_id)
    expected_name = FIXTURES[style][0]
    hook_input = json.dumps({"session_id": session_id})

    output = run(hook_input, styles_dir=styles_dir)

    parsed = json.loads(output)
    assert expected_name in parsed["hookSpecificOutput"]["additionalContext"]
