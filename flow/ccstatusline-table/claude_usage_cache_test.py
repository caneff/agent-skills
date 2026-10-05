#!/usr/bin/env python3
"""The status line writes Claude's usage cache (#1436): each render of
`table-statusline.py` stores the session JSON's `rate_limits` block where
`multi-axis-code-review/claude-usage-gate.py` reads it.

Seam: the status line's command line (session JSON on stdin) against a
temporary `$HOME`; the cache file is the observable.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LINE = os.path.join(HERE, "table-statusline.py")


def render(home, session):
    env = {"HOME": home, "PATH": os.environ["PATH"]}
    p = subprocess.run([sys.executable, LINE], input=json.dumps(session), env=env,
                       capture_output=True, text=True, cwd=home)
    assert p.returncode == 0, p.stderr
    path = os.path.join(home, ".cache/agent-skills/claude-usage.json")
    return json.load(open(path)) if os.path.exists(path) else None


def main():
    resets = int(time.time()) + 7200
    limits = {"five_hour": {"used_percentage": 12.5, "resets_at": resets},
              "seven_day": {"used_percentage": 42, "resets_at": resets + 86400}}
    with tempfile.TemporaryDirectory() as home:
        assert render(home, {"model": {"display_name": "Opus 4.8"}}) is None, "absent block wrote a cache"
        got = render(home, {"rate_limits": limits})
        assert got["rate_limits"] == limits, got
        assert abs(got["fetched"] - time.time()) < 60, got
        again = render(home, {"model": {"display_name": "Opus 4.8"}})
        assert again["rate_limits"] == limits, "a render without the block clobbered the cache"
        bad = render(home, {"rate_limits": {"five_hour": {"used_percentage": "x", "resets_at": 1}}})
        assert bad["rate_limits"] == limits, "a malformed block clobbered the cache"
        half = {"five_hour": {"used_percentage": 100.5, "resets_at": resets},
                "seven_day": {"used_percentage": 50, "resets_at": resets + 86400}}
        assert render(home, {"rate_limits": half})["rate_limits"] == limits, \
            "a block with one malformed window was stored in part"
        idle = {"five_hour": {"used_percentage": 3, "resets_at": resets},
                "seven_day": {"used_percentage": 1, "resets_at": resets + 86400}}
        assert render(home, {"rate_limits": idle})["rate_limits"] == limits, \
            "an idle session's lower reading of the same window replaced a higher one"
        rolled = {"five_hour": {"used_percentage": 2, "resets_at": resets + 18000},
                  "seven_day": limits["seven_day"]}
        got = render(home, {"rate_limits": rolled})["rate_limits"]
        assert got["five_hour"]["used_percentage"] == 2, "a new window did not replace the old"
        older = {"five_hour": limits["five_hour"]}
        assert render(home, {"rate_limits": older})["rate_limits"]["five_hour"]["used_percentage"] == 2, \
            "a window older than the cached one replaced it"
    print("ok")


if __name__ == "__main__":
    main()
