"""Tests for error-handling's ruff+bandit merge (#1744; was `audit.py`'s `_selfcheck`)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from audit import parse_findings  # noqa: E402

BLE = "Do not catch blind exception: `Exception`"
RUFF = json.dumps([
    {"filename": "sample.py", "location": {"row": 14}, "code": "BLE001", "message": BLE},
    {"filename": "sample.py", "location": {"row": 23}, "code": "SIM105",
     "message": "Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`"},
    {"filename": "sample.py", "location": {"row": 25}, "code": "BLE001", "message": BLE},
])
BANDIT = json.dumps({"results": [
    {"filename": "sample.py", "line_number": line, "test_id": "B110", "issue_text": "Try, Except, Pass detected."}
    for line in (14, 25)
]})


@pytest.fixture(scope="module")
def rows():
    return parse_findings(RUFF, BANDIT)


def test_three_lines_three_rows(rows):
    assert sorted(r["line"] for r in rows) == [14, 23, 25]
    assert all(r["failure"] == "" for r in rows)


@pytest.mark.parametrize("line,category,codes", [
    (14, "bare-except", ["B110", "BLE001"]),  # ruff BLE001 + bandit B110 merge
    (23, "try-except-pass", ["SIM105"]),      # ruff only
    (25, "bare-except", ["B110", "BLE001"]),
])
def test_row_per_line(rows, line, category, codes):
    row = next(r for r in rows if r["line"] == line)
    assert row["category"] == category
    assert row["extra"]["codes"] == codes


def test_bare_except_is_a_fix(rows):
    assert next(r for r in rows if r["line"] == 14)["bucket"] == "fix"


def test_empty_inputs_are_no_rows():
    assert parse_findings(json.dumps([]), json.dumps({"results": []})) == []
