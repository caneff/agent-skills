"""Tests for the activation switch: settings.json wiring (issue #299)."""
import copy
import json

from activate import (
    SESSION_START_CMD,
    STOP_CMD,
    USER_PROMPT_SUBMIT_CMD,
    install,
    main,
    uninstall,
)

REALISTIC = {
    "outputStyle": "Clarity and Grace",
    "hooks": {
        "SessionStart": [
            {"hooks": [{"type": "command", "command": "bash skills-sync.sh"}]}
        ],
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "echo Output style: ..."}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": "bash some-other-stop-hook.sh"}]}
        ],
    },
}


def test_install_appends_session_start_and_replaces_user_prompt_submit():
    new, state = install(REALISTIC)

    ss_commands = [
        entry["hooks"][0]["command"] for entry in new["hooks"]["SessionStart"]
    ]
    assert ss_commands == ["bash skills-sync.sh", SESSION_START_CMD]
    assert new["hooks"]["UserPromptSubmit"] == [
        {"hooks": [{"type": "command", "command": USER_PROMPT_SUBMIT_CMD}]}
    ]
    assert new["outputStyle"] == "default"


def test_install_appends_stop_reminder_keeping_existing_stop_entries():
    new, state = install(REALISTIC)

    stop_commands = [
        entry["hooks"][0]["command"] for entry in new["hooks"]["Stop"]
    ]
    assert stop_commands == ["bash some-other-stop-hook.sh", STOP_CMD]


def test_install_captures_saved_state():
    _, state = install(REALISTIC)
    assert state == {
        "prev_output_style": "Clarity and Grace",
        "prev_user_prompt_submit": REALISTIC["hooks"]["UserPromptSubmit"],
    }


def test_install_does_not_mutate_input():
    before = copy.deepcopy(REALISTIC)
    install(REALISTIC)
    assert REALISTIC == before


def test_install_is_structurally_idempotent():
    once, _ = install(REALISTIC)
    twice, _ = install(once)
    assert twice["hooks"]["SessionStart"] == once["hooks"]["SessionStart"]
    assert twice["hooks"]["UserPromptSubmit"] == once["hooks"]["UserPromptSubmit"]
    assert twice["hooks"]["Stop"] == once["hooks"]["Stop"]


def test_install_creates_missing_hooks_keys():
    new, state = install({})
    assert new["hooks"]["SessionStart"][0]["hooks"][0]["command"] == SESSION_START_CMD
    assert new["hooks"]["UserPromptSubmit"] == [
        {"hooks": [{"type": "command", "command": USER_PROMPT_SUBMIT_CMD}]}
    ]
    assert new["hooks"]["Stop"] == [
        {"hooks": [{"type": "command", "command": STOP_CMD}]}
    ]
    assert state == {"prev_output_style": None, "prev_user_prompt_submit": []}


def test_round_trip_realistic():
    new, state = install(REALISTIC)
    assert uninstall(new, state) == REALISTIC


def test_round_trip_no_output_style_key():
    settings = {
        "hooks": {
            "SessionStart": [],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}],
        }
    }
    new, state = install(settings)
    assert uninstall(new, state) == settings


def test_round_trip_no_hooks_key():
    settings = {"outputStyle": "plain"}
    new, state = install(settings)
    assert uninstall(new, state) == settings


def _write(path, data):
    path.write_text(json.dumps(data))


def test_cli_install_then_uninstall_round_trips(tmp_path, capsys):
    settings_path = tmp_path / "settings.json"
    state_path = tmp_path / "state.json"
    _write(settings_path, REALISTIC)

    main(["install", "--settings-path", str(settings_path), "--state-path", str(state_path)])
    assert state_path.exists()
    installed = json.loads(settings_path.read_text())
    assert installed["outputStyle"] == "default"

    main(["install", "--settings-path", str(settings_path), "--state-path", str(state_path)])
    out = capsys.readouterr().out
    assert "already active" in out
    # no-op: settings untouched by the second call
    assert json.loads(settings_path.read_text()) == installed

    main(["uninstall", "--settings-path", str(settings_path), "--state-path", str(state_path)])
    assert not state_path.exists()
    assert json.loads(settings_path.read_text()) == REALISTIC


def test_cli_uninstall_without_state_is_noop(tmp_path, capsys):
    settings_path = tmp_path / "settings.json"
    state_path = tmp_path / "state.json"
    _write(settings_path, REALISTIC)

    main(["uninstall", "--settings-path", str(settings_path), "--state-path", str(state_path)])
    out = capsys.readouterr().out
    assert "not active" in out
    assert json.loads(settings_path.read_text()) == REALISTIC
