#!/usr/bin/env python3
"""Codex rate-limit cell for the table statusline.

Reads `usedPercent`/`resetsAt` from a cache file under `$CODEX_HOME`
(default `~/.codex`), refreshing it inline when older than `CACHE_TTL` by
calling the Codex app-server's `account/rateLimits/read` over a
line-delimited JSON-RPC handshake spoken to a spawned `codex app-server`
process — the app-server's own HTTP GET underneath, no model turn — instead
of tailing a rollout `.jsonl`. An OpenAI maintainer said plainly that the
rollout format is not a durable surface (openai/codex#43593); the
app-server API is. See
`docs/research/2026-09-16-codex-usage-percentage-sources.md` for the full
trail.

Prints one cell — `12% 6d`, primary window then secondary when the plan has
one — or nothing at all: no cache, no live reply within the timeout, or a
window whose reset has already passed (that percentage describes a window
that no longer exists). No stale case is marked, because a failed refresh
never falls back to old numbers — it prints nothing instead.

Stdin is ignored (the table fans the session JSON out to every helper).

A second consumer: `implement/codex-usage-gate.py` imports this file and
calls `read_cache`, `fetch_live`, `write_cache`, `valid_window` and sets
`RPC_TIMEOUT`. Renaming or changing the contract of any of them breaks that
gate, which fails closed (exit 30) and skips every Codex pass.
"""

from __future__ import annotations

import json
import math
import os
import select
import subprocess
import sys
import time
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
CACHE_PATH = CODEX_HOME / "usage-cache.json"
CACHE_TTL = 30 * 60
# Below table-statusline.py's own 1.5s subprocess timeout, so a slow refresh
# gets a chance to return None and let write_cache run instead of being
# SIGKILLed mid-call — a kill leaves nothing cached, so the next 10s tick
# pays the same cold-spawn cost again.
RPC_TIMEOUT = 1.3
WINDOWS = ("primary", "secondary")


def countdown(seconds: float) -> str:
    """Leading unit only — `6d`, `3h`, `20m` — matching the Claude cell."""
    if seconds <= 0:
        return ""
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return "1m"


def valid_window(limit: object) -> tuple[float, float] | None:
    """`(usedPercent, resetsAt)` of one rate-limit window, or None when the
    window is not a dict holding two finite, non-boolean numbers with a
    non-negative percentage. `json.loads` accepts NaN and Infinity, and
    `True` is an `int`; none of them is a reading. The one validator behind
    both the cell below and `implement/codex-usage-gate.py`."""
    if not isinstance(limit, dict):
        return None
    pct, resets = limit.get("usedPercent"), limit.get("resetsAt")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (pct, resets)):
        return None
    if pct < 0:
        return None
    return pct, resets


def window(limit: object, now: float) -> str:
    parsed = valid_window(limit)
    if parsed is None:
        return ""
    pct, resets = parsed
    if resets <= now:
        return ""  # window already rolled over; the percentage is about nothing
    return " ".join(x for x in (f"{int(pct)}%", countdown(resets - now)) if x)


def cell(limits: dict | None, now: float) -> str:
    if not limits:
        return ""
    parts = [window(limits.get(k), now) for k in WINDOWS]
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
    limits = {k: data[k] for k in WINDOWS if k in data}
    return limits or None


def write_cache(limits: dict, now: float) -> None:
    """Write the cache atomically — a reader must never see a torn file.

    Two ticks racing (both find the cache stale, both refresh, both write)
    would otherwise let a concurrent `read_cache` open a half-written file;
    write-to-temp-then-rename is atomic on the same filesystem.
    """
    payload = {"fetchedAt": now, **{k: limits.get(k) for k in WINDOWS}}
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def _send(stdin, obj: dict) -> bool:
    try:
        stdin.write(json.dumps(obj).encode() + b"\n")
        stdin.flush()
        return True
    except (BrokenPipeError, OSError):
        return False


def _replies(fd: int, deadline: float):
    """Yield decoded JSON objects read from `fd` until nothing arrives before `deadline`.

    Reads raw bytes and splits lines ourselves instead of `select()`ing a
    buffered file object: a `select()` on the fd only says a *read* would
    return data, not that a *line* is ready. When two lines land in one
    `read()` — an unsolicited notification riding along with the reply we
    want — a buffered `readline()` can hand back just the first and leave
    the second sitting in its own internal buffer, invisible to the next
    `select()`, which then burns the rest of the deadline waiting for bytes
    that already arrived.
    """
    buf = b""
    while True:
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except OSError:
            return
        if not ready:
            return
        chunk = os.read(fd, 65536)
        if not chunk:
            return
        buf += chunk


def fetch_live() -> dict | None:
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
        )
    except OSError:
        return None

    deadline = time.monotonic() + RPC_TIMEOUT
    replies = _replies(proc.stdout.fileno(), deadline)

    def until(target_id: int) -> dict | None:
        for obj in replies:
            if obj.get("id") == target_id:
                return obj
        return None

    try:
        if not _send(
            proc.stdin,
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
            },
        ):
            return None
        if until(1) is None:
            return None
        if not _send(proc.stdin, {"jsonrpc": "2.0", "method": "initialized", "params": {}}):
            return None
        if not _send(
            proc.stdin,
            {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}},
        ):
            return None
        reply = until(2)
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
    main()
