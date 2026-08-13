#!/usr/bin/env python3
"""Activation switch: wire the blind-test hooks into settings.json (issue #299).

Manual usage:
  python3 style-blind-test/activate.py install
  python3 style-blind-test/activate.py uninstall

install() appends a SessionStart harness hook (keeping any existing
SessionStart entries, e.g. skills-sync), and replaces UserPromptSubmit
entirely with the harness hook -- disabling the existing "stay in that
voice" echo reminder for the duration of the test, since it would fire
every turn and contaminate the blind guess. It also sets outputStyle to
"default" (blanking the native style). uninstall() restores all three.

Criterion 4 (a real session shows the injected style live) is a MANUAL
check: run `install`, start a Claude Code session, confirm the style is
active, then run `uninstall` when done.
"""
import argparse
import copy
import json
from pathlib import Path

SESSION_START_CMD = "python3 /home/caneff/.agents/skills/style-blind-test/session_start.py"
USER_PROMPT_SUBMIT_CMD = "python3 /home/caneff/.agents/skills/style-blind-test/user_prompt_submit.py"

DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_STATE_PATH = Path.home() / ".claude" / "style-blind-test" / "activation-state.json"

_SS_ENTRY = {"hooks": [{"type": "command", "command": SESSION_START_CMD}]}
_UPS_ENTRY = {"hooks": [{"type": "command", "command": USER_PROMPT_SUBMIT_CMD}]}


def install(settings: dict) -> tuple[dict, dict]:
    new = copy.deepcopy(settings)
    hooks = new.setdefault("hooks", {})
    ss = hooks.setdefault("SessionStart", [])
    prev_ups = copy.deepcopy(hooks.get("UserPromptSubmit", []))

    if not any(e["hooks"][0]["command"] == SESSION_START_CMD for e in ss):
        ss.append(copy.deepcopy(_SS_ENTRY))
    hooks["UserPromptSubmit"] = [copy.deepcopy(_UPS_ENTRY)]

    state = {
        "prev_output_style": settings.get("outputStyle"),
        "prev_user_prompt_submit": prev_ups,
    }
    new["outputStyle"] = "default"
    return new, state


def uninstall(settings: dict, state: dict) -> dict:
    new = copy.deepcopy(settings)

    if state["prev_output_style"] is None:
        new.pop("outputStyle", None)
    else:
        new["outputStyle"] = state["prev_output_style"]

    hooks = new.setdefault("hooks", {})
    hooks["UserPromptSubmit"] = copy.deepcopy(state["prev_user_prompt_submit"])
    hooks["SessionStart"] = [
        e for e in hooks.get("SessionStart", []) if e["hooks"][0]["command"] != SESSION_START_CMD
    ]
    if not hooks["SessionStart"] and not hooks["UserPromptSubmit"]:
        new.pop("hooks", None)
    return new


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--settings-path", type=Path, default=DEFAULT_SETTINGS_PATH)
    common.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)

    parser = argparse.ArgumentParser(prog="activate", parents=[common])
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install", parents=[common])
    subparsers.add_parser("uninstall", parents=[common])

    args = parser.parse_args(argv)

    if args.command == "install":
        if args.state_path.exists():
            print("already active")
            return
        settings = _read_json(args.settings_path)
        new, state = install(settings)
        _write_json(args.settings_path, new)
        _write_json(args.state_path, state)
    else:
        if not args.state_path.exists():
            print("not active")
            return
        settings = _read_json(args.settings_path)
        state = _read_json(args.state_path)
        new = uninstall(settings, state)
        _write_json(args.settings_path, new)
        args.state_path.unlink()


if __name__ == "__main__":
    main()
