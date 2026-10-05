#!/usr/bin/env python3
"""Claude plan-usage cache (#1436): the status line's `rate_limits` block, kept for scripts.

Claude Code hands `rate_limits.five_hour` / `.seven_day` (`used_percentage`, `resets_at`
epoch seconds) only to the status-line command, never to a script. `table-statusline.py`
calls `write_cache` on every render, so the file holds the newest reading any session on
this box has rendered; `multi-axis-code-review/claude-usage-gate.py` imports this file and
calls `read_windows`. No credential read and no OAuth usage endpoint
(see `usage-segment.sh`): this stores only what the client already handed the status line.

The file is `~/.cache/agent-skills/claude-usage.json`:
`{"fetched": <epoch>, "rate_limits": {"five_hour": {...}, "seven_day": {...}}}`.

`write_cache` stores a block only when it has a window and every window in it is
well-formed, so an absent block (non-subscriber, older Claude Code) or a bad one never
replaces a good reading. Each window merges with the cached one: the same `resets_at`
keeps the higher percentage, so an idle session re-rendering an old, lower reading cannot
lower a newer session's; a later `resets_at` is a new window and replaces it; an earlier
one is a stale session and is ignored. `fetched` is when a render wrote, not the age of
the reading, which is why the merge exists. `read_windows` raises `Unreadable`, naming
the cause, for a missing, unparseable, future-dated or older-than-`CACHE_TTL` file or a
malformed or reset window: unknown, never headroom.
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


def merge(old: object, new: dict) -> dict:
    """`new` unless `old` is the same window with a higher reading, or a later window."""
    prev = valid_window(old)
    if prev is None:
        return new
    cur = valid_window(new)
    if cur[1] < prev[1] or (cur[1] == prev[1] and cur[0] < prev[0]):
        return old
    return new


def write_cache(session: object, now: float) -> None:
    """Merge `session["rate_limits"]` into the cache; never raises."""
    try:
        block = session.get("rate_limits") if isinstance(session, dict) else None
        if not isinstance(block, dict):
            return
        present = {k: block[k] for k in WINDOWS if k in block}
        if not present or any(valid_window(w) is None for w in present.values()):
            return
        path = cache_path()
        try:
            old = json.loads(path.read_text())["rate_limits"]
            old = old if isinstance(old, dict) else {}
        except (OSError, ValueError, KeyError, TypeError):
            old = {}
        limits = {k: merge(old.get(k), w) for k, w in present.items()}
        for k in WINDOWS:
            if k not in limits and valid_window(old.get(k)) is not None:
                limits[k] = old[k]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"fetched": now, "rate_limits": limits}))
        os.replace(tmp, path)
    except Exception:
        pass


class Unreadable(Exception):
    """No usable reading; the message names why."""


def read_windows(now: float) -> list[tuple[float, float]]:
    """[(used_percentage, resets_at)] per cached window, or raise Unreadable.

    A present but malformed window, or one whose reset has passed (its percentage
    describes a window that no longer exists), voids the whole reading; an absent
    window is simply not there, and no window at all is unreadable.
    """
    try:
        data = json.loads(cache_path().read_text())
    except FileNotFoundError:
        raise Unreadable(f"no cache file ({cache_path()})") from None
    except (OSError, ValueError) as exc:
        raise Unreadable(f"cache unreadable: {exc}") from None
    fetched = data.get("fetched") if isinstance(data, dict) else None
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    if isinstance(fetched, bool) or not isinstance(fetched, (int, float)):
        raise Unreadable("cache has no fetched stamp")
    if fetched > now:
        raise Unreadable("cache stamped in the future")
    if now - fetched > CACHE_TTL:
        raise Unreadable(f"cache older than {CACHE_TTL // 60} minutes")
    if not isinstance(limits, dict):
        raise Unreadable("cache has no rate_limits")
    out = []
    for key in WINDOWS:
        if key not in limits:
            continue
        parsed = valid_window(limits[key])
        if parsed is None:
            raise Unreadable(f"{key} window malformed")
        if parsed[1] <= now:
            raise Unreadable(f"{key} window already reset")
        out.append(parsed)
    if not out:
        raise Unreadable("cache holds no window")
    return out
