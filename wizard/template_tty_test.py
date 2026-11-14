"""wizard/template.sh's `ask` at a real pseudo-terminal: `--secret` hides
what is typed, a plain prompt echoes it (#1731, C7).

`template.test.sh` pipes stdin, where `read -s` is unobservable; this suite
types into a pty after the prompt is up, so the terminal's own echo is what
the assertions read. It still cannot see a human's terminal emulator.
"""
import os
import pty
import select
import subprocess
import termios
import time
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template.sh"


def _read_until(fd, needle, deadline):
    out = b""
    while needle not in out and time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if ready:
            try:
                out += os.read(fd, 4096)
            except OSError:  # the child closed the pty
                break
    return out


def _echo_off(fd, deadline):
    """Wait until the line discipline stops echoing, or the deadline passes."""
    while time.monotonic() < deadline:
        if not termios.tcgetattr(fd)[3] & termios.ECHO:
            return True
        time.sleep(0.01)
    return False


def type_answer(tmp_path, *ask_args, wait_for_echo_off):
    """Run `ask` in a pty, type `hush` once the prompt is up; returns
    (what the terminal showed after the prompt, the value ask stored)."""
    lib = tmp_path / "lib.sh"
    lib.write_text(TEMPLATE.read_text().split("\n# STAGES", 1)[0] + "\n")
    out_file = tmp_path / "out"
    script = 'source ./lib.sh; ask "$@"; printf "%s" "$KEY_VAL" >out'
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["bash", "-c", script, "_", *ask_args], cwd=tmp_path,
        stdin=slave, stdout=slave, stderr=slave, close_fds=True,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
             "ENV_FILE": str(tmp_path / ".env"), "TERM": "dumb"})
    os.close(slave)
    try:
        deadline = time.monotonic() + 5
        _read_until(master, b"Prompt:", deadline)
        if wait_for_echo_off:
            _echo_off(master, deadline)
        os.write(master, b"hush\n")
        shown = _read_until(master, b"\n", time.monotonic() + 5)
        proc.wait(timeout=5)
    finally:
        proc.kill()
        os.close(master)
    return shown.decode("utf-8", "replace"), out_file.read_text()


def test_secret_ask_does_not_echo(tmp_path):
    shown, stored = type_answer(tmp_path, "--secret", "KEY_VAL", "Prompt:",
                                wait_for_echo_off=True)
    assert stored == "hush"
    assert "hush" not in shown


def test_plain_ask_echoes(tmp_path):
    shown, stored = type_answer(tmp_path, "KEY_VAL", "Prompt:",
                                wait_for_echo_off=False)
    assert stored == "hush"
    assert "hush" in shown
