#!/usr/bin/env python3
"""Codex rate-limit cell for the table statusline.

Codex writes a `rate_limits` snapshot into the current session's rollout log
after every turn, so the newest `~/.codex/sessions/**/rollout-*.jsonl` holds the
last figure the Codex CLI itself was told. That is the only source read here:
no credential read and no call to OpenAI's usage endpoint, matching the rule
`usage-segment.sh` follows for Claude's own numbers.

Prints one cell — `12% 6d`, primary window then secondary when the plan has
one — or nothing at all when there is no usable snapshot. A percentage whose
window has already reset describes a window that no longer exists, so it prints
nothing rather than a stale number; one over a day old keeps its figure but
carries a `?`, because Codex only refreshes it when Codex runs.

Stdin is ignored (the table fans the session JSON out to every helper).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SESSIONS = Path.home() / ".codex" / "sessions"
TAIL_BYTES = 256 * 1024  # enough for many turns' worth of trailing events
STALE_AFTER = 24 * 3600


def newest_rollout(root: Path) -> Path | None:
    """Newest rollout log, walking year/month/day newest-first.

    The tree is date-partitioned, so descending the highest-named directory at
    each level reaches today's logs without stat-ing every session ever
    recorded. Falls back down the list when a day's directory holds no rollout.
    """
    def descend(d: Path, depth: int) -> Path | None:
        try:
            kids = sorted((p for p in d.iterdir() if p.is_dir()), reverse=True)
        except OSError:
            return None
        if depth == 0:
            files = [p for p in d.glob("rollout-*.jsonl")]
            return max(files, key=lambda p: p.stat().st_mtime) if files else None
        for k in kids:
            if (hit := descend(k, depth - 1)) is not None:
                return hit
        return None

    return descend(root, 3)


def last_rate_limits(path: Path) -> dict | None:
    """The final `rate_limits` object in the log, read from the tail."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            chunk = fh.read()
    except OSError:
        return None
    # A partial first line is expected after seeking into the middle of one.
    for line in reversed(chunk.decode("utf-8", "replace").splitlines()):
        if '"rate_limits"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (found := find(row)) is not None:
            return found
    return None


def find(node: object) -> dict | None:
    """First `rate_limits` mapping anywhere in a decoded event."""
    if isinstance(node, dict):
        if isinstance(node.get("rate_limits"), dict):
            return node["rate_limits"]
        for v in node.values():
            if (hit := find(v)) is not None:
                return hit
    elif isinstance(node, list):
        for v in node:
            if (hit := find(v)) is not None:
                return hit
    return None


def countdown(seconds: float) -> str:
    """Leading unit only — `6d`, `3h`, `20m` — matching the Claude cell."""
    if seconds <= 0:
        return ""
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return "1m"


def window(limit: object, now: float, stale: bool) -> str:
    if not isinstance(limit, dict):
        return ""
    pct = limit.get("used_percent")
    resets = limit.get("resets_at")
    if not isinstance(pct, (int, float)) or not isinstance(resets, (int, float)):
        return ""
    if resets <= now:
        return ""  # window already rolled over; the percentage is about nothing
    mark = "?" if stale else ""
    return " ".join(x for x in (f"{int(pct)}%{mark}", countdown(resets - now)) if x)


def cell(limits: dict | None, snapshot_age: float, now: float) -> str:
    if not limits:
        return ""
    stale = snapshot_age > STALE_AFTER
    parts = [window(limits.get(k), now, stale) for k in ("primary", "secondary")]
    return " · ".join(p for p in parts if p)


def main() -> None:
    sys.stdin.buffer.read()
    path = newest_rollout(SESSIONS)
    if path is None:
        return
    now = time.time()
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return
    if text := cell(last_rate_limits(path), age, now):
        sys.stdout.write(text)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        now = 1_000_000.0
        lim = {
            "primary": {"used_percent": 12.9, "resets_at": now + 6 * 86400 + 3600},
            "secondary": None,
        }
        assert cell(lim, 60, now) == "12% 6d", cell(lim, 60, now)
        assert cell(lim, 2 * 86400, now) == "12%? 6d"
        both = {
            "primary": {"used_percent": 94.0, "resets_at": now + 2 * 86400},
            "secondary": {"used_percent": 6.0, "resets_at": now + 3 * 3600},
        }
        assert cell(both, 60, now) == "94% 2d · 6% 3h", cell(both, 60, now)
        # A window whose reset has passed describes nothing.
        assert cell({"primary": {"used_percent": 80.0, "resets_at": now - 1}}, 60, now) == ""
        assert cell(None, 60, now) == ""
        assert cell({}, 60, now) == ""
        assert cell({"primary": {"used_percent": 5.0}}, 60, now) == ""
        assert countdown(45) == "1m" and countdown(0) == ""
        # The real shape Codex writes, straight from a rollout log.
        real = {
            "limit_id": "codex", "limit_name": None,
            "primary": {"used_percent": 0.0, "window_minutes": 10080,
                        "resets_at": now + 86400},
            "secondary": None, "plan_type": "plus",
        }
        assert cell(real, 60, now) == "0% 1d", cell(real, 60, now)
        assert find({"payload": {"rate_limits": {"primary": None}}}) == {"primary": None}
        assert find({"a": [{"b": 1}]}) is None
        print("ok")
    else:
        main()
