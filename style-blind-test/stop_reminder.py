#!/usr/bin/env python3
"""Stop hook: loud reminder to log a blind guess every N turns (issue #316).

Reads hook JSON (session_id) on stdin, bumps a per-session assistant-turn
counter file, and once per REMINDER_INTERVAL crossing (25/50/75...) fires a
desktop toast (WSL powershell.exe, sandcastle-watch/toast.ps1 pattern) and a
terminal bell. Reveals no style and never touches the guess log -- this
module never imports assignment or capture.
"""
import json
import subprocess
import sys
from pathlib import Path

from score import QUALIFYING_TURNS

REMINDER_INTERVAL = QUALIFYING_TURNS

REMINDER_MESSAGE = "Blind test -- log your guess (gs)"

DEFAULT_STATE_DIR = Path.home() / ".claude" / "style-blind-test" / "turns"

_SKILL_DIR = Path(__file__).resolve().parent.parent / "sandcastle-watch"
_TOAST_SCRIPT = _SKILL_DIR / "toast.ps1"


def should_fire(prev_count: int, new_count: int, interval: int = REMINDER_INTERVAL) -> bool:
    """True iff [prev_count, new_count] crosses a multiple of `interval` (>0)."""
    if interval <= 0:
        return False
    return new_count // interval > prev_count // interval


def _read_state(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    parts = path.read_text().split()
    count = int(parts[0]) if parts else 0
    last_fired = int(parts[1]) if len(parts) > 1 else 0
    return count, last_fired


def _write_state(path: Path, count: int, last_fired: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{count} {last_fired}\n")


def _notify() -> None:
    # ponytail: fire-and-forget, best-effort. A dead notification is not a
    # reason to fail the Stop hook.
    try:
        sys.stderr.write("\a")
        sys.stderr.flush()
    except Exception:
        pass

    try:
        import shutil

        if shutil.which("powershell.exe") is None:
            return
        wslpath = subprocess.run(
            ["wslpath", "-w", str(_TOAST_SCRIPT)], capture_output=True, text=True
        )
        if wslpath.returncode != 0:
            return
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                wslpath.stdout.strip(),
                "-Title",
                "Blind test",
                "-Body",
                REMINDER_MESSAGE,
            ],
            capture_output=True,
        )
    except Exception:
        pass


def run(hook_input: str, state_dir: Path = DEFAULT_STATE_DIR) -> bool:
    payload = json.loads(hook_input)
    session_id = payload["session_id"]
    state_path = Path(state_dir) / session_id

    prev_count, last_fired = _read_state(state_path)
    new_count = prev_count + 1

    fired = should_fire(prev_count, new_count) and new_count > last_fired
    if fired:
        last_fired = new_count
        _notify()

    _write_state(state_path, new_count, last_fired)
    return fired


def main() -> None:
    run(sys.stdin.read())


if __name__ == "__main__":
    main()
