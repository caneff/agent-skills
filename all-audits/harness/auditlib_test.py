"""Tests for auditlib (#1744; were `auditlib.py`'s `_selfcheck`).

The excluded-dirs drift check had never run before this file: `auditlib.py`
carried no `audit.py` name, so `tests/all.sh` never found its `--selfcheck`.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import auditlib  # noqa: E402


def test_finding_failure_defaults_empty():
    assert auditlib.finding("cut", "a.py", 1, "x", "s")["failure"] == ""


def test_finding_extra_is_kept():
    assert auditlib.finding("cut", "a.py", 1, "x", "s", foo=1)["extra"] == {"foo": 1}


def test_walk_source_prunes_excluded_dirs(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "vendor" / "skip.py").write_text("")
    (tmp_path / "pkg" / "keep.py").write_text("")
    assert auditlib.walk_source(str(tmp_path)) == ["pkg/keep.py"]


def test_excluded_dirs_json_mirror_is_not_stale():
    mirror = os.path.join(os.path.dirname(__file__), "excluded-dirs.json")
    with open(mirror, encoding="utf-8") as f:
        assert set(json.load(f)) == auditlib.EXCLUDED_DIRS, (
            "excluded-dirs.json is stale: re-run "
            "`python3 auditlib.py --write-json-mirror excluded-dirs.json`")


def test_run_cli_has_no_selfcheck_flag(tmp_path, capsys):
    """`--selfcheck` is an ordinary file argument now: it is read, not special-cased."""
    with pytest.raises(FileNotFoundError):
        auditlib.run_cli(["audit.py", "--selfcheck"], lambda text: [])


def test_run_cli_prints_one_json_line_per_row(tmp_path, capsys):
    path = tmp_path / "in.txt"
    path.write_text("abc", encoding="utf-8")
    auditlib.run_cli(["audit.py", str(path)], lambda text: [{"n": len(text)}, {"n": 0}])
    assert capsys.readouterr().out.splitlines() == ['{"n": 3}', '{"n": 0}']
