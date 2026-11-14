"""Tests for docstring-coverage's parser (#1744; was `audit.py`'s `_selfcheck`)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from audit import parse_coverage  # noqa: E402

INTERROGATE = "---------------- RESULT: FAILED (minimum: 80.0%, actual: 50.0%) ----------------"


def test_d103_row_carries_the_interrogate_coverage():
    ruff_json = json.dumps([{
        "filename": "sample.py", "location": {"row": 9}, "code": "D103",
        "message": "Missing docstring in public function",
    }])
    rows = parse_coverage(ruff_json, INTERROGATE)
    assert len(rows) == 1, rows
    row = rows[0]
    assert (row["bucket"], row["file"], row["line"], row["category"]) == (
        "document", "sample.py", 9, "missing-function-docstring")
    assert row["extra"]["coverage"] == 50.0
    assert row["summary"] == "missing function docstring at sample.py:9"
    assert row["failure"] == ""


def test_no_ruff_hits_is_no_rows():
    assert parse_coverage(json.dumps([]), INTERROGATE) == []
