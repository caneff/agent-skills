#!/usr/bin/env python3
"""The Claude usage gate (#1436): `claude-usage-gate.py` reads the cache the status
line writes (`flow/ccstatusline-table/helpers/claude-usage.py`) and answers with an exit
status the review step branches on — 0 proceed, 20 capped (spawn no axis), 30 unknown
(no fresh, well-formed reading; the 429 path covers the spawn).

Seam: the script's command line — stdout line and exit status — against a cache file
under a temporary `$HOME`.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

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


def run(content):
    """(exit status, stdout) with `content` (a dict, a str, or None) as the cache file."""
    with tempfile.TemporaryDirectory() as home:
        if content is not None:
            path = os.path.join(home, ".cache/agent-skills/claude-usage.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as f:
                f.write(content if isinstance(content, str) else json.dumps(content))
        p = subprocess.run([sys.executable, GATE], env={"HOME": home, "PATH": "/nonexistent"},
                           capture_output=True, text=True)
        return p.returncode, p.stdout


def check(name, got, status, needle=""):
    assert got[0] == status and needle in got[1], f"{name}: want {status} {needle!r}, got {got}"


def main():
    check("under the ceiling", run(cache(win(40), win(50))), 0, "50%")
    check("zero is a reading, not an absence", run(cache(win(0), win(0))), 0)
    check("one window alone", run(cache(five=win(10))), 0)
    resets = time.time() + 3 * HOUR
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    check("worst window blocks, reset named", run(cache(win(10), win(96, resets))), 20, when)
    check("exactly at the ceiling blocks", run(cache(win(95))), 20)
    check("missing cache", run(None), 30)
    check("stale cache", run(cache(win(10), age=11 * 60)), 30)
    check("fresh enough", run(cache(win(10), age=9 * 60)), 0)
    check("not json", run("{oops"), 30)
    check("no windows at all", run(cache()), 30)
    check("malformed window voids the reading", run(cache(win(10), {"used_percentage": "x", "resets_at": 1})), 30)
    check("percentage out of range", run(cache(win(120))), 30)
    check("a window that has reset is not a reading", run(cache(win(99, time.time() - 5))), 30)
    check("no fetched stamp", run({"rate_limits": {"five_hour": win(10)}}), 30)
    print("ok")


if __name__ == "__main__":
    main()
