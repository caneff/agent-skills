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
HELPER = Path(__file__).resolve().parent.parent / "flow/ccstatusline-table/helpers/codex-usage.py"

PROCEED, WARN, CAPPED, UNKNOWN = 0, 10, 20, 30


def load_helper():
    spec = importlib.util.spec_from_file_location("codex_usage", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reading(limits: object, now: float) -> tuple[float, float] | None:
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
        if not isinstance(win, dict):
            return None
        pct, resets = win.get("usedPercent"), win.get("resetsAt")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (pct, resets)):
            return None
        if resets <= now:
            return None
        if worst is None or pct > worst[0]:
            worst = (pct, resets)
    return worst


def main() -> int:
    helper = load_helper()
    now = time.time()
    found = reading(helper.read_cache(now), now)
    if found is None:
        live = helper.fetch_live()
        if live is not None:
            helper.write_cache(live, now)
            found = reading(live, now)
    if found is None:
        print("codex usage unknown: no fresh, readable usage cache and the live fetch failed")
        return UNKNOWN
    pct, resets = found
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    if pct >= 100:
        print(f"codex usage {pct:g}% — capped, resets {when}")
        return CAPPED
    if pct >= WARN_PERCENT:
        print(f"codex usage {pct:g}% — at or above {WARN_PERCENT}%, resets {when}")
        return WARN
    print(f"codex usage {pct:g}% — ok, resets {when}")
    return PROCEED


if __name__ == "__main__":
    sys.exit(main())
