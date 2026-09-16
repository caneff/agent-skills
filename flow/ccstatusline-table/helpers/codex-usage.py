#!/usr/bin/env python3
"""Codex rate-limit cell for the table statusline.

Reads `usedPercent`/`resetsAt` from a cache file under `$CODEX_HOME`
(default `~/.codex`), refreshing it inline when older than `CACHE_TTL` by
calling the Codex app-server's `account/rateLimits/read` — a plain HTTP GET
under the hood, no model turn — instead of tailing a rollout `.jsonl`. An
OpenAI maintainer said plainly that the rollout format is not a durable
surface (openai/codex#43593); the app-server API is. See
`docs/research/2026-09-16-codex-usage-percentage-sources.md` for the full
trail.

Prints one cell — `12% 6d`, primary window then secondary when the plan has
one — or nothing at all: no cache, no live reply within the timeout, or a
window whose reset has already passed (that percentage describes a window
that no longer exists). No stale case is marked, because a failed refresh
never falls back to old numbers — it prints nothing instead.

Stdin is ignored (the table fans the session JSON out to every helper).
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
CACHE_PATH = CODEX_HOME / "usage-cache.json"
CACHE_TTL = 30 * 60
RPC_TIMEOUT = 1.5


def countdown(seconds: float) -> str:
    """Leading unit only — `6d`, `3h`, `20m` — matching the Claude cell."""
    if seconds <= 0:
        return ""
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return "1m"


def window(limit: object, now: float) -> str:
    if not isinstance(limit, dict):
        return ""
    pct = limit.get("usedPercent")
    resets = limit.get("resetsAt")
    if not isinstance(pct, (int, float)) or not isinstance(resets, (int, float)):
        return ""
    if resets <= now:
        return ""  # window already rolled over; the percentage is about nothing
    return " ".join(x for x in (f"{int(pct)}%", countdown(resets - now)) if x)


def cell(limits: dict | None, now: float) -> str:
    if not limits:
        return ""
    parts = [window(limits.get(k), now) for k in ("primary", "secondary")]
    return " · ".join(p for p in parts if p)


def read_cache(now: float) -> dict | None:
    """Cached `primary`/`secondary` limits, or None if missing/stale."""
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None
    fetched = data.get("fetchedAt")
    if not isinstance(fetched, (int, float)) or now - fetched > CACHE_TTL:
        return None
    limits = {k: data[k] for k in ("primary", "secondary") if k in data}
    return limits or None


def write_cache(limits: dict, now: float) -> None:
    payload = {"fetchedAt": now, **{k: limits.get(k) for k in ("primary", "secondary")}}
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload))
    except OSError:
        pass


def fetch_live(timeout: float = RPC_TIMEOUT) -> dict | None:
    """`rateLimits` from a fresh `codex app-server` round trip, or None.

    Speaks the app-server's line-delimited JSON-RPC: `initialize`, the
    `initialized` notification, then `account/rateLimits/read`. Stdin stays
    open until the matching-id reply for each request arrives — closing it
    early makes the process exit before answering, which looks exactly like
    a silent failure.
    """
    try:
        proc = subprocess.Popen(
            ["codex", "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError:
        return None

    deadline = time.monotonic() + timeout

    def send(obj: dict) -> bool:
        try:
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def recv_until(target_id: int) -> dict | None:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                ready, _, _ = select.select([proc.stdout], [], [], remaining)
            except OSError:
                return None
            if not ready:
                return None
            line = proc.stdout.readline()
            if not line:
                return None
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("id") == target_id:
                return obj

    try:
        if not send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "ccstatusline-table",
                        "title": "ccstatusline-table",
                        "version": "0.0.0",
                    }
                },
            }
        ):
            return None
        if recv_until(1) is None:
            return None
        if not send({"jsonrpc": "2.0", "method": "initialized", "params": {}}):
            return None
        if not send(
            {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}}
        ):
            return None
        reply = recv_until(2)
        if reply is None:
            return None
        result = reply.get("result")
        limits = result.get("rateLimits") if isinstance(result, dict) else None
        return limits if isinstance(limits, dict) else None
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait()


def main() -> None:
    sys.stdin.buffer.read()
    now = time.time()
    limits = read_cache(now)
    if limits is None:
        limits = fetch_live()
        if limits is None:
            return
        write_cache(limits, now)
    if text := cell(limits, now):
        sys.stdout.write(text)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        now = 1_000_000.0
        lim = {
            "primary": {"usedPercent": 12.9, "resetsAt": now + 6 * 86400 + 3600},
            "secondary": None,
        }
        assert cell(lim, now) == "12% 6d", cell(lim, now)
        both = {
            "primary": {"usedPercent": 94.0, "resetsAt": now + 2 * 86400},
            "secondary": {"usedPercent": 6.0, "resetsAt": now + 3 * 3600},
        }
        assert cell(both, now) == "94% 2d · 6% 3h", cell(both, now)
        # A window whose reset has passed describes nothing.
        assert cell({"primary": {"usedPercent": 80.0, "resetsAt": now - 1}}, now) == ""
        assert cell(None, now) == ""
        assert cell({}, now) == ""
        assert cell({"primary": {"usedPercent": 5.0}}, now) == ""
        assert countdown(45) == "1m" and countdown(0) == ""
        # The real shape the app-server returns.
        real = {
            "primary": {"usedPercent": 0.0, "windowDurationMins": 10080, "resetsAt": now + 86400},
            "secondary": None,
        }
        assert cell(real, now) == "0% 1d", cell(real, now)

        import tempfile

        with tempfile.TemporaryDirectory() as d:
            CACHE_PATH = Path(d) / "usage-cache.json"
            globals()["CACHE_PATH"] = CACHE_PATH
            assert read_cache(now) is None  # no file yet
            write_cache(both, now)
            assert read_cache(now) == both
            assert read_cache(now + CACHE_TTL + 1) is None  # older than 30m
            CACHE_PATH.write_text("not json")
            assert read_cache(now) is None  # corrupt cache fails soft

        print("ok")
    else:
        main()
