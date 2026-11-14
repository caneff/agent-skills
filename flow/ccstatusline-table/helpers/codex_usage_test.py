"""codex-usage.py: cell rendering, the cache, and the reply reader.

Replaces the old `--selftest` mode (#1753). The cache path is redirected to a
temp dir per test; a fresh cache must never spawn `codex`.
"""
import importlib.util
import io
import os
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("codex_usage", HERE / "codex-usage.py")
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)

NOW = 1_000_000.0
BOTH = {
    "primary": {"usedPercent": 94.0, "resetsAt": NOW + 2 * 86400},
    "secondary": {"usedPercent": 6.0, "resetsAt": NOW + 3 * 3600},
}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "usage-cache.json"  # parent absent: the first-run case
    monkeypatch.setattr(cu, "CACHE_PATH", path)
    return path


def test_cell_primary_only():
    lim = {"primary": {"usedPercent": 12.9, "resetsAt": NOW + 6 * 86400 + 3600}, "secondary": None}
    assert cu.cell(lim, NOW) == "12% 6d"


def test_cell_both_windows():
    assert cu.cell(BOTH, NOW) == "94% 2d · 6% 3h"


@pytest.mark.parametrize("limits", [
    {"primary": {"usedPercent": 80.0, "resetsAt": NOW - 1}},  # reset already passed
    None,
    {},
    {"primary": {"usedPercent": 5.0}},
])
def test_cell_blank_when_no_live_window(limits):
    assert cu.cell(limits, NOW) == ""


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1.0])
def test_cell_rejects_non_window_percentages(bad):
    assert cu.cell({"primary": {"usedPercent": bad, "resetsAt": NOW + 86400}}, NOW) == ""


def test_cell_rejects_boolean_reset():
    assert cu.cell({"primary": {"usedPercent": 5.0, "resetsAt": True}}, NOW) == ""


def test_valid_window():
    future = NOW + 86400
    assert cu.valid_window({"usedPercent": 5, "resetsAt": future}) == (5, future)
    assert cu.valid_window({"usedPercent": -1, "resetsAt": future}) is None


def test_countdown():
    assert cu.countdown(45) == "1m"
    assert cu.countdown(0) == ""
    assert cu.countdown(3 * 3600 + 5) == "3h"


def test_cell_real_app_server_shape():
    real = {
        "primary": {"usedPercent": 0.0, "windowDurationMins": 10080, "resetsAt": NOW + 86400},
        "secondary": None,
    }
    assert cu.cell(real, NOW) == "0% 1d"


def test_cache_round_trip_and_expiry(cache):
    assert cu.read_cache(NOW) is None  # no file yet
    cu.write_cache(BOTH, NOW)
    assert cu.read_cache(NOW) == BOTH
    assert cu.read_cache(NOW + cu.CACHE_TTL + 1) is None  # older than 30m


def test_corrupt_cache_fails_soft(cache):
    cache.parent.mkdir(parents=True)
    cache.write_text("not json")
    assert cu.read_cache(NOW) is None


def test_replies_keeps_reply_after_unsolicited_line():
    # A reply landing in the same read() as an unsolicited line ahead of it
    # must not be lost (a select()-on-buffered-readline loses exactly this).
    r, w = os.pipe()
    try:
        os.write(w, b'{"method":"notify","params":{}}\n{"id":9,"result":{"ok":true}}\n')
        got = list(cu._replies(r, time.monotonic() + 1.0))
    finally:
        os.close(r)
        os.close(w)
    assert got == [{"method": "notify", "params": {}}, {"id": 9, "result": {"ok": True}}]


def _run_main(monkeypatch):
    class Stdin:
        buffer = io.BytesIO(b"")

    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(sys, "stdout", out)
    cu.main()
    return out.getvalue()


def test_fresh_cache_never_spawns_codex(cache, tmp_path, monkeypatch):
    sentinel = tmp_path / "spawned"
    fake = tmp_path / "bin" / "codex"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\ntouch "{sentinel}"\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}:{os.environ['PATH']}")
    now = time.time()
    live = {"primary": {"usedPercent": 94.0, "resetsAt": now + 2 * 86400 + 60},
            "secondary": {"usedPercent": 6.0, "resetsAt": now + 3 * 3600 + 60}}
    cu.write_cache(live, now)
    assert _run_main(monkeypatch) == "94% 2d · 6% 3h"
    assert not sentinel.exists(), "fresh cache spawned codex"


def test_stale_cache_and_failed_refresh_prints_nothing(cache, monkeypatch):
    monkeypatch.setattr(cu, "fetch_live", lambda: None)
    assert _run_main(monkeypatch) == ""


def test_stale_cache_refreshes_and_writes(cache, monkeypatch):
    live = {"primary": {"usedPercent": 3.0, "resetsAt": time.time() + 3 * 3600 + 60}, "secondary": None}
    monkeypatch.setattr(cu, "fetch_live", lambda: live)
    assert _run_main(monkeypatch) == "3% 3h"
    assert cu.read_cache(time.time()) is not None
