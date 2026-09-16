#!/usr/bin/env python3
"""Record the raw bytes a dictation paste delivers, with the Kitty keyboard
protocol and bracketed paste turned on (as herdr and Claude Code do).

Every chunk is appended to pasteprobe.log as it arrives. Ctrl+C quits, in
either its legacy byte or its Kitty encoding.
"""
import os
import select
import sys
import termios
import time
import tty

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pasteprobe.log")
QUIT = (b"\x03", b"\x1b[99;5u")


def read_chunk(fd, first_timeout=None):
    ready, _, _ = select.select([fd], [], [], first_timeout)
    if not ready:
        return b""
    data = os.read(fd, 4096)
    while select.select([fd], [], [], 0.05)[0]:
        data += os.read(fd, 4096)
    return data


def main():
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    out = sys.stdout
    with open(LOG, "a") as log:
        try:
            tty.setraw(fd)
            # herdr v0.9.0 default: 1|2|4; 31 only when a pane asks to report all keys.
            flags = sys.argv[1] if len(sys.argv) > 1 else "7"
            out.write(f"\x1b[?2004h\x1b[>{flags}u\x1b[?u")
            out.flush()
            reply = read_chunk(fd, 1.0)
            kitty = "active" if reply.startswith(b"\x1b[?") and reply.endswith(b"u") else "not active"
            log.write(f"--- {time.strftime('%H:%M:%S')} flags {flags} kitty: {kitty} (reply {reply!r})\n")
            log.flush()
            out.write(f"Kitty keyboard protocol: {kitty}\r\n")
            out.write("Dictate one short phrase with Wispr now. Ctrl+C quits.\r\n\r\n")
            out.flush()
            start = time.monotonic()
            while True:
                data = read_chunk(fd)
                stamp = f"{time.monotonic() - start:7.3f}s"
                log.write(f"{stamp} {data!r}\n")
                log.flush()
                out.write(f"{stamp} {data!r}\r\n")
                out.flush()
                if data in QUIT:
                    return
        finally:
            out.write("\x1b[<u\x1b[?2004l")
            out.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    main()
