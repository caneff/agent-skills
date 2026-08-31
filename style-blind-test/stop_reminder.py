#!/usr/bin/env python3
"""Stop hook: loud reminder to log a blind guess every N turns (issue #316).

Reads hook JSON (session_id) on stdin, bumps a per-session assistant-turn
counter file, and once per REMINDER_INTERVAL crossing (10/20/30...) fires a
desktop toast (WSL powershell.exe, via the local toast.ps1) and a
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


def toast_marker_path(state_dir: Path) -> Path:
    """The last-toast marker lives as a sibling of the turns dir it's derived from."""
    return Path(state_dir).parent / "last_toast"


LAST_TOAST_PATH = toast_marker_path(DEFAULT_STATE_DIR)

_TOAST_SCRIPT = Path(__file__).resolve().parent / "toast.ps1"


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


def write_last_toast(session_id: str, cwd: str | None, path: Path = LAST_TOAST_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{session_id}\n{cwd or ''}\n")


def read_last_toast(path: Path = LAST_TOAST_PATH) -> tuple[str, str | None] | None:
    path = Path(path)
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    if not lines or not lines[0]:
        return None
    session_id = lines[0]
    cwd = lines[1] if len(lines) > 1 and lines[1] else None
    return session_id, cwd


def _notify(session_id: str, cwd: str | None = None) -> None:
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
        proj = Path(cwd).name if cwd else "?"
        short_id = session_id[:8]
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
                f"{REMINDER_MESSAGE}\n{proj} · {short_id}",
                "-Duration",
                "long",
            ],
            capture_output=True,
        )
    except Exception:
        pass


def run(hook_input: str, state_dir: Path = DEFAULT_STATE_DIR) -> bool:
    payload = json.loads(hook_input)
    session_id = payload["session_id"]
    cwd = payload.get("cwd")
    state_path = Path(state_dir) / session_id

    prev_count, last_fired = _read_state(state_path)
    new_count = prev_count + 1

    fired = should_fire(prev_count, new_count) and new_count > last_fired
    if fired:
        last_fired = new_count
        _notify(session_id, cwd)
        write_last_toast(session_id, cwd, path=toast_marker_path(state_dir))

    _write_state(state_path, new_count, last_fired)
    return fired


def main() -> None:
    run(sys.stdin.read())


if __name__ == "__main__":
    main()
