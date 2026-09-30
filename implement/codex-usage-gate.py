#!/usr/bin/env python3
"""Codex usage preflight (#1204): may a Codex run start?

Run before every Codex launch — the merge-time adversarial pass
(`SKILL.md` § The merge step 3) and the Codex lane (`codex-lane.md`). Reads
the usage cache `flow/ccstatusline-table/helpers/codex-usage.py` keeps under
`$CODEX_HOME`; when that cache is missing, stale or unreadable it refreshes
it through the helper's own live fetch, which still answers at the cap.

One line on stdout, and an exit status the caller branches on:

  0   proceed — usage is under WARN_PERCENT
  10  tell Chris before starting — usage is at or above WARN_PERCENT
  20  capped — usage is at 100%; launch nothing, write no duration row
  30  unknown — no fresh, well-formed reading; launch nothing

A missing, stale or malformed reading is 30, never 0: it is not headroom.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

WARN_PERCENT = 80
# The helper's 1.3s RPC_TIMEOUT is tuned to a statusline tick; a loaded box
# answers in 0.6-1.2s, and a spurious timeout here skips a pass (exit 30).
REFRESH_TIMEOUT = 5.0
HELPER = Path(__file__).resolve().parent.parent / "flow/ccstatusline-table/helpers/codex-usage.py"

PROCEED, WARN, CAPPED, UNKNOWN = 0, 10, 20, 30


def load_helper():
    spec = importlib.util.spec_from_file_location("codex_usage", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def worst_window(helper, limits: object, now: float) -> tuple[float, float] | None:
    """(worst usedPercent, its resetsAt) across the windows, or None.

    A window that is present but malformed, or whose reset has passed (its
    percentage describes a window that no longer exists), voids the whole
    reading; an absent window (`secondary: null`) is simply not there.
    """
    if not isinstance(limits, dict):
        return None
    worst = None
    for key in ("primary", "secondary"):
        win = limits.get(key)
        if win is None:
            continue
        parsed = helper.valid_window(win)
        if parsed is None:
            return None
        pct, resets = parsed
        if resets <= now:
            return None
        if worst is None or pct > worst[0]:
            worst = (pct, resets)
    return worst


def check() -> tuple[int, str]:
    helper = load_helper()
    helper.RPC_TIMEOUT = REFRESH_TIMEOUT
    now = time.time()
    worst = worst_window(helper, helper.read_cache(now), now)
    if worst is None:
        live = helper.fetch_live()
        if live is not None:
            helper.write_cache(live, now)
            worst = worst_window(helper, live, now)
    if worst is None:
        return UNKNOWN, "codex usage unknown: no fresh, readable usage cache and the live fetch failed"
    pct, resets = worst
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    if pct >= 100:
        return CAPPED, f"codex usage {pct:g}% — capped, resets {when}"
    if pct >= WARN_PERCENT:
        return WARN, f"codex usage {pct:g}% — at or above {WARN_PERCENT}%, resets {when}"
    return PROCEED, f"codex usage {pct:g}% — ok, resets {when}"


def main() -> int:
    # Any failure is exit 30: a crash's own exit 1 is a status neither caller
    # has a rule for, and an unread reading is not headroom.
    try:
        status, line = check()
    except Exception as exc:
        status, line = UNKNOWN, f"codex usage unknown: {type(exc).__name__}: {exc}"
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
