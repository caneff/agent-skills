#!/usr/bin/env python3
"""Log the raw bytes the terminal sends for key combos, and flag collisions.

Asks the terminal for the Kitty keyboard protocol first, so a terminal that
honours it reports enhanced codes; one that ignores it sends legacy bytes.
Space skips a combo (e.g. one VS Code swallows). Results also go to keyprobe.log.
"""
import os
import select
import sys
import termios
import tty

COMBOS = [
    "Enter", "Shift+Enter", "Ctrl+Enter", "Alt+Enter",
    "Backspace", "Ctrl+Backspace", "Alt+Backspace",
    "Tab", "Shift+Tab", "Ctrl+I",
    "Esc", "Ctrl+[",
    "Ctrl+J", "Ctrl+M", "Ctrl+H",
    "Ctrl+B", "Ctrl+Left", "Alt+Left",
]
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keyprobe.log")


def read_chunk(fd, first_timeout=None):
    ready, _, _ = select.select([fd], [], [], first_timeout)
    if not ready:
        return b""
    data = os.read(fd, 64)
    while select.select([fd], [], [], 0.05)[0]:
        data += os.read(fd, 64)
    return data


def main():
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    out = sys.stdout
    results = []
    try:
        tty.setraw(fd)
        # Push all Kitty enhancement flags, then query the active flags.
        out.write("\x1b[>31u\x1b[?u")
        out.flush()
        reply = read_chunk(fd, 1.0)
        kitty = "active" if b"?" in reply and reply.endswith(b"u") else "not active"
        out.write(f"Kitty keyboard protocol: {kitty} (reply {reply!r})\r\n")
        out.write("Press each combo once. Space skips. Ctrl+C quits without saving.\r\n\r\n")
        termios.tcflush(fd, termios.TCIFLUSH)
        for combo in COMBOS:
            out.write(f"  {combo:<16} ... ")
            out.flush()
            data = read_chunk(fd)
            if data == b"\x03":
                out.write("quit\r\n")
                return
            if data == b" ":
                results.append((combo, None))
                out.write("skipped\r\n")
            else:
                results.append((combo, data))
                out.write(f"{data!r}\r\n")
    finally:
        out.write("\x1b[<u")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    by_bytes = {}
    for combo, data in results:
        if data is not None:
            by_bytes.setdefault(data, []).append(combo)
    lines = [f"kitty: {kitty}"]
    lines += [f"{c:<16} {d!r}" if d is not None else f"{c:<16} skipped" for c, d in results]
    lines.append("")
    lines.append("Collisions (these combos are indistinguishable):")
    collisions = [v for v in by_bytes.values() if len(v) > 1]
    lines += [f"  {' = '.join(v)}" for v in collisions] or ["  none"]
    text = "\n".join(lines) + "\n"
    print("\n" + text)
    with open(LOG, "a") as f:
        f.write(text + "---\n")
    print(f"Logged to {LOG}")


if __name__ == "__main__":
    main()
