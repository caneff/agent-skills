"""The Claude usage gate (#1436): `claude-usage-gate.py` reads the cache the
status line writes (`flow/ccstatusline-table/helpers/claude-usage.py`); its
docstring defines the exit statuses.

Seam: the script's command line — stdout line and exit status — against a
cache file under a temporary `$HOME`.
"""
import json
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "claude-usage-gate.py")
HOUR = 3600


def win(pct, resets=None):
    return {"used_percentage": pct, "resets_at": resets if resets is not None else time.time() + 2 * HOUR}


def cache(five=None, seven=None, age=0):
    limits = {}
    if five is not None:
        limits["five_hour"] = five
    if seven is not None:
        limits["seven_day"] = seven
    return {"fetched": time.time() - age, "rate_limits": limits}


def run(home, content):
    """(exit status, stdout) with `content` (a dict, a str, or None) as the cache file."""
    if content is not None:
        path = home / ".cache/agent-skills/claude-usage.json"
        path.parent.mkdir(parents=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))
    p = subprocess.run([sys.executable, GATE], env={"HOME": str(home), "PATH": "/nonexistent"},
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def cases():
    """(id, cache content, exit status, needle); built per call so the
    timestamps are relative to now."""
    resets = time.time() + 3 * HOUR
    later = time.time() + 3 * 86400
    soon = time.time() + HOUR
    return [
        ("under the ceiling", cache(win(40), win(50)), 0, "50%"),
        ("zero is a reading, not an absence", cache(win(0), win(0)), 0, ""),
        ("one window alone", cache(five=win(10)), 0, ""),
        ("worst window blocks, reset named", cache(win(10), win(96, resets)), 20, when(resets)),
        ("exactly at the ceiling blocks", cache(win(95)), 20, ""),
        ("missing cache", None, 30, ""),
        ("stale cache", cache(win(10), age=11 * 60), 30, ""),
        ("fresh enough", cache(win(10), age=9 * 60), 0, ""),
        ("not json", "{oops", 30, ""),
        ("no windows at all", cache(), 30, ""),
        ("malformed window voids the reading", cache(win(10), {"used_percentage": "x", "resets_at": 1}), 30, ""),
        ("percentage out of range", cache(win(120)), 30, ""),
        ("a window that has reset is not a reading", cache(win(99, time.time() - 5)), 30, ""),
        ("future-dated stamp", cache(win(10), age=-HOUR), 30, "future"),
        ("crash is exit 30, not 1", cache(win(10, 1e300)), 30, ""),
        ("block names when it lifts: the later reset of the blocking windows",
         cache(win(99, soon), win(96, later)), 20, when(later)),
        ("only a blocking window's reset counts", cache(win(99, soon), win(10, later)), 20, when(soon)),
        ("cause: missing", None, 30, "no cache file"),
        ("cause: stale", cache(win(10), age=11 * 60), 30, "older than"),
        ("cause: reset window", cache(win(99, time.time() - 5)), 30, "already reset"),
        ("no fetched stamp", {"rate_limits": {"five_hour": win(10)}}, 30, ""),
    ]


@pytest.mark.parametrize("content,status,needle", [c[1:] for c in cases()], ids=[c[0] for c in cases()])
def test_gate_exit_status_and_stdout(tmp_path, content, status, needle):
    got = run(tmp_path, content)
    assert got[0] == status and needle in got[1], f"want {status} {needle!r}, got {got}"
