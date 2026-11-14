"""Tests for duplication's jscpd parser (#1744; was `audit.py`'s `_selfcheck`)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from audit import parse_jscpd  # noqa: E402


def test_one_duplicate_pair_is_one_consolidate_row():
    sample = json.dumps({"duplicates": [{
        "firstFile": {"name": "a.py", "start": 4, "end": 19},
        "secondFile": {"name": "b.py", "start": 6, "end": 21},
        "format": "python", "fragment": "...", "lines": 16, "tokens": 92,
    }]})
    rows = parse_jscpd(sample)
    assert len(rows) == 1, rows
    row = rows[0]
    assert (row["file"], row["line"], row["category"], row["bucket"]) == ("a.py", 4, "token-clone", "consolidate")
    assert row["extra"]["clone_tokens"] == 92
    assert "b.py:6" in row["summary"]
    assert row["failure"] == ""
    assert row["owner"] == "b.py:6"


def test_no_duplicates_is_no_rows():
    assert parse_jscpd(json.dumps({"duplicates": []})) == []
