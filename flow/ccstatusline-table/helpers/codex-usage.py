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

        import io as _io
        import os as _os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            # A cache path whose parent doesn't exist yet — the first-run case.
            CACHE_PATH = Path(d) / "sub" / "usage-cache.json"
            assert read_cache(now) is None  # no file yet
            write_cache(both, now)
            assert read_cache(now) == both
            assert read_cache(now + CACHE_TTL + 1) is None  # older than 30m
            CACHE_PATH.write_text("not json")
            assert read_cache(now) is None  # corrupt cache fails soft

            # _replies must not lose a reply that lands in the same read() as
            # an unsolicited line ahead of it — the regression this helper
            # exists to catch (a select()-on-buffered-readline loses exactly
            # this).
            r, w = _os.pipe()
            _os.write(
                w,
                b'{"method":"notify","params":{}}\n{"id":9,"result":{"ok":true}}\n',
            )
            got = list(_replies(r, time.monotonic() + 1.0))
            _os.close(r)
            _os.close(w)
            assert got == [
                {"method": "notify", "params": {}},
                {"id": 9, "result": {"ok": True}},
            ], got

            # A fresh cache must not spawn `codex` at all — the common-case promise.
            sentinel = Path(d) / "spawned"
            fake_codex = Path(d) / "codex"
            fake_codex.write_text(f'#!/bin/sh\ntouch "{sentinel}"\nexit 1\n')
            fake_codex.chmod(0o755)
            env_path = _os.environ.get("PATH", "")
            _os.environ["PATH"] = f"{d}:{env_path}"
            try:
                real_now = time.time()
                write_cache(both, real_now)
                assert read_cache(real_now) == both

                class _FakeStdin:
                    buffer = _io.BytesIO(b"")

                old_stdin, old_stdout = sys.stdin, sys.stdout
                sys.stdin, sys.stdout = _FakeStdin(), _io.StringIO()
                try:
                    main()
                finally:
                    sys.stdin, sys.stdout = old_stdin, old_stdout
                assert not sentinel.exists(), "fresh cache spawned codex"
            finally:
                _os.environ["PATH"] = env_path

        print("ok")
    else:
        main()
