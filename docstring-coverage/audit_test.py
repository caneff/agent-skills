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


def test_cli_reports_not_applicable_on_a_repo_with_no_python(tmp_path):
    import subprocess
    (tmp_path / "index.js").write_text("")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "audit.py"), "--applicable", str(tmp_path)],
                       capture_output=True, text=True)
    assert (r.returncode, r.stdout.strip()) == (3, "not applicable: JavaScript"), r.stdout + r.stderr


def test_cli_applicable_exits_zero_with_python_source(tmp_path):
    import subprocess
    (tmp_path / "a.py").write_text("")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "audit.py"), "--applicable", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "applicable", r.stdout + r.stderr
