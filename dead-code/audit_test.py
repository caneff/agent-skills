"""Tests for dead-code's vulture parser (#1744; was `audit.py`'s `_selfcheck`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from audit import parse_vulture  # noqa: E402

SAMPLE = "\n".join([
    "foo.py:12: unused function 'helper' (60% confidence)",
    "bar.py:3: unused import 'os' (90% confidence)",
])


def test_parse_vulture_rows():
    rows = parse_vulture(SAMPLE)
    assert [(r["file"], r["line"], r["category"], r["extra"]["confidence"]) for r in rows] == [
        ("foo.py", 12, "unused-function", 60),
        ("bar.py", 3, "unused-import", 90),
    ]
    assert all(r["bucket"] == "unsure" and r["failure"] == "" for r in rows)
    assert "helper" in rows[0]["summary"] and "os" in rows[1]["summary"]


def test_parse_vulture_skips_lines_outside_the_contract():
    assert parse_vulture("foo.py:1: unreachable code after 'return' (100% confidence)\n") == []

