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
