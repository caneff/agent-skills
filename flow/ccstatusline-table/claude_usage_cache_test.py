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
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
LINE = os.path.join(HERE, "table-statusline.py")
NO_BLOCK = {"model": {"display_name": "Opus 4.8"}}


def render(home, session):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    p = subprocess.run([sys.executable, LINE], input=json.dumps(session), env=env,
                       capture_output=True, text=True, cwd=home)
    assert p.returncode == 0, p.stderr
    path = home / ".cache/agent-skills/claude-usage.json"
    return json.loads(path.read_text()) if path.exists() else None


@pytest.fixture
def resets():
    return int(time.time()) + 7200


@pytest.fixture
def limits(resets):
    return {"five_hour": {"used_percentage": 12.5, "resets_at": resets},
            "seven_day": {"used_percentage": 42, "resets_at": resets + 86400}}


@pytest.fixture
def seeded(tmp_path, limits):
    """A home whose cache already holds `limits`."""
    render(tmp_path, {"rate_limits": limits})
    return tmp_path


def test_absent_block_writes_no_cache(tmp_path):
    assert render(tmp_path, NO_BLOCK) is None, "absent block wrote a cache"


def test_block_is_stored_with_a_fetch_time(tmp_path, limits):
    got = render(tmp_path, {"rate_limits": limits})
    assert got["rate_limits"] == limits, got
    assert abs(got["fetched"] - time.time()) < 60, got


def test_render_without_the_block_keeps_the_cache(seeded, limits):
    again = render(seeded, NO_BLOCK)
    assert again["rate_limits"] == limits, "a render without the block clobbered the cache"


def test_malformed_block_keeps_the_cache(seeded, limits):
    bad = render(seeded, {"rate_limits": {"five_hour": {"used_percentage": "x", "resets_at": 1}}})
    assert bad["rate_limits"] == limits, "a malformed block clobbered the cache"


def test_block_with_one_malformed_window_is_not_stored_in_part(seeded, limits, resets):
    half = {"five_hour": {"used_percentage": 100.5, "resets_at": resets},
            "seven_day": {"used_percentage": 50, "resets_at": resets + 86400}}
    assert render(seeded, {"rate_limits": half})["rate_limits"] == limits, \
        "a block with one malformed window was stored in part"


def test_idle_sessions_lower_reading_of_the_same_window_is_ignored(seeded, limits, resets):
    idle = {"five_hour": {"used_percentage": 3, "resets_at": resets},
            "seven_day": {"used_percentage": 1, "resets_at": resets + 86400}}
    assert render(seeded, {"rate_limits": idle})["rate_limits"] == limits, \
        "an idle session's lower reading of the same window replaced a higher one"


def test_a_new_window_replaces_the_old_and_an_older_one_does_not(seeded, limits, resets):
    rolled = {"five_hour": {"used_percentage": 2, "resets_at": resets + 18000},
              "seven_day": limits["seven_day"]}
    got = render(seeded, {"rate_limits": rolled})["rate_limits"]
    assert got["five_hour"]["used_percentage"] == 2, "a new window did not replace the old"
    older = {"five_hour": limits["five_hour"]}
    assert render(seeded, {"rate_limits": older})["rate_limits"]["five_hour"]["used_percentage"] == 2, \
        "a window older than the cached one replaced it"
