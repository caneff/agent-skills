"""Tests for the SessionStart hook entrypoint (issue #295)."""
import json

from assignment import STYLES, assignment
from session_start import run

FIXTURE_BODIES = {
    "clarity-and-grace": "Clarity and grace fixture body.\n",
    "orwell-ste": "Orwell STE fixture body.\n",
    "plain-speak": "Plain speak fixture body.\n",
}


def _make_styles_dir(tmp_path):
    styles_dir = tmp_path / "output-styles"
    styles_dir.mkdir()
    for style, body in FIXTURE_BODIES.items():
        (styles_dir / f"{style}.md").write_text(body)
    return styles_dir


def _find_session_id_for_style(target_style):
    for i in range(500):
        sid = f"session-{i}"
        style, _ = assignment(sid)
        if style == target_style:
            return sid
    raise AssertionError(f"no session id in range produced style {target_style!r}")


def test_non_default_style_emits_additional_context_with_file_body(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for_style("clarity-and-grace")
    hook_input = json.dumps({"session_id": session_id, "source": "startup"})

    output = run(hook_input, styles_dir=styles_dir)

    assert output is not None
    parsed = json.loads(output)
    assert parsed == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": FIXTURE_BODIES["clarity-and-grace"],
        }
    }


def test_file_body_read_as_is_byte_for_byte(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for_style("plain-speak")
    hook_input = json.dumps({"session_id": session_id, "source": "clear"})

    output = run(hook_input, styles_dir=styles_dir)

    parsed = json.loads(output)
    expected = (styles_dir / "plain-speak.md").read_bytes()
    assert parsed["hookSpecificOutput"]["additionalContext"].encode() == expected


def test_default_style_emits_nothing(tmp_path):
    styles_dir = _make_styles_dir(tmp_path)
    session_id = _find_session_id_for_style("default")
    hook_input = json.dumps({"session_id": session_id, "source": "resume"})

    output = run(hook_input, styles_dir=styles_dir)

    assert output is None
