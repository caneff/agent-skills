#!/usr/bin/env python3
"""Claude plan-usage cache (#1436): the status line's `rate_limits` block, kept for scripts.

Claude Code hands `rate_limits.five_hour` / `.seven_day` (`used_percentage`, `resets_at`
epoch seconds) only to the status-line command, never to a script. `table-statusline.py`
calls `write_cache` on every render, so the file holds the newest reading any session on
this box has rendered; `multi-axis-code-review/claude-usage-gate.py` imports this file and
calls `read_cache` and `worst_window`. No credential read and no OAuth usage endpoint
(see `usage-segment.sh`): this stores only what the client already handed the status line.

The file is `~/.cache/agent-skills/claude-usage.json`:
`{"fetched": <epoch>, "rate_limits": {"five_hour": {...}, "seven_day": {...}}}`.

`write_cache` stores a block only when at least one window is well-formed and drops any
malformed window, so an absent block (non-subscriber, older Claude Code) or a bad one
never replaces a good reading. `read_cache` returns None for a missing, unparseable,
future-dated or older-than-`CACHE_TTL` file: unknown, never headroom.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

WINDOWS = ("five_hour", "seven_day")
# A render happens every status-line tick (10s) in any live session; ten minutes with no
# render means no session is feeding the cache, so the reading no longer describes now.
CACHE_TTL = 10 * 60


def cache_path() -> Path:
    return Path.home() / ".cache/agent-skills/claude-usage.json"


def valid_window(win: object) -> tuple[float, float] | None:
    """(used_percentage, resets_at) of a well-formed window, else None."""
    if not isinstance(win, dict):
        return None
    pct, resets = win.get("used_percentage"), win.get("resets_at")
    for v in (pct, resets):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
    if not 0 <= pct <= 100:
        return None
    return float(pct), float(resets)


def write_cache(session: object, now: float) -> None:
    """Store `session["rate_limits"]`'s well-formed windows; never raises."""
    try:
        block = session.get("rate_limits") if isinstance(session, dict) else None
        if not isinstance(block, dict):
            return
        limits = {k: block[k] for k in WINDOWS if valid_window(block.get(k)) is not None}
        if not limits:
            return
        path = cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"fetched": now, "rate_limits": limits}))
        os.replace(tmp, path)
    except Exception:
        pass


def read_cache(now: float) -> dict | None:
    """The cached `rate_limits` dict, or None when absent, malformed or stale."""
    try:
        data = json.loads(cache_path().read_text())
        fetched, limits = data["fetched"], data["rate_limits"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(fetched, bool) or not isinstance(fetched, (int, float)):
        return None
    if not 0 <= now - fetched <= CACHE_TTL or not isinstance(limits, dict):
        return None
    return limits


def worst_window(limits: object, now: float) -> tuple[float, float] | None:
    """(worst used_percentage, its resets_at) across the windows, or None.

    A present but malformed window, or one whose reset has passed (its percentage
    describes a window that no longer exists), voids the whole reading; an absent
    window is simply not there, and no window at all is None.
    """
    if not isinstance(limits, dict):
        return None
    worst = None
    for key in WINDOWS:
        if key not in limits:
            continue
        parsed = valid_window(limits[key])
        if parsed is None or parsed[1] <= now:
            return None
        if worst is None or parsed[0] > worst[0]:
            worst = parsed
    return worst
