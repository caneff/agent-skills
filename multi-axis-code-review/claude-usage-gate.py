#!/usr/bin/env python3
"""Claude usage gate (#1436): may the review axes spawn?

Run before `SKILL.md` § 4 spawns the axes. Reads the cache the status line writes
(`flow/ccstatusline-table/helpers/claude-usage.py`); it never reads credentials or the
OAuth usage endpoint. One line on stdout, and an exit status the caller branches on:

  0   proceed — the worst window is under BLOCK_PERCENT
  20  capped — the worst window is at or above BLOCK_PERCENT; spawn no axis. The line
      carries the reset time of the last blocking window, which goes into the report
  30  unknown — the line names why (no cache, older than the helper's CACHE_TTL, a
      malformed or reset window); this is not headroom. The caller still spawns (the 429
      path in `SKILL.md` covers a limit hit mid-round) and says the usage was unread

BLOCK_PERCENT leaves a few points because a three-axis round spends several percent of a
window; at 100 it would start axes that die on their first turn.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent / "flow/ccstatusline-table/helpers/claude-usage.py"
BLOCK_PERCENT = 95

PROCEED, CAPPED, UNKNOWN = 0, 20, 30


def load_helper():
    spec = importlib.util.spec_from_file_location("claude_usage", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check() -> tuple[int, str]:
    helper = load_helper()
    now = time.time()
    try:
        windows = helper.read_windows(now)
    except helper.Unreadable as exc:
        return UNKNOWN, f"claude usage unknown: {exc}"
    pct = max(p for p, _ in windows)
    if pct >= BLOCK_PERCENT:
        # The block lifts when every window at or above the ceiling has reset.
        resets = max(r for p, r in windows if p >= BLOCK_PERCENT)
        verdict, status = f"at or above {BLOCK_PERCENT}%", CAPPED
    else:
        resets = max(r for p, r in windows if p == pct)
        verdict, status = "ok", PROCEED
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    return status, f"claude usage {pct:g}% {verdict}, resets {when}"


def main() -> int:
    # Any failure is exit 30: a crash's own exit 1 is a status the caller has no rule for.
    try:
        status, line = check()
    except Exception as exc:
        status, line = UNKNOWN, f"claude usage unknown: {type(exc).__name__}: {exc}"
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
