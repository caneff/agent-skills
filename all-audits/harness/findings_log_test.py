"""Tests for `findings_log`: the one reader and writer of a findings.jsonl."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import findings_log  # noqa: E402


def test_write_then_read_round_trips_rows(tmp_path):
    path = str(tmp_path / "findings.jsonl")
    rows = [{"file": "a.py", "line": 3, "summary": "s"}, {"status": "setup_failure", "reason": "é"}]
    findings_log.write(path, rows)
    log = findings_log.read(path)
    assert log.rows == rows and log.corrupt == []


def test_empty_log_reads_as_no_rows_and_no_corruption(tmp_path):
    path = str(tmp_path / "findings.jsonl")
    findings_log.write(path, [])
    assert findings_log.read(path) == findings_log.Log([], [])


def test_a_corrupt_line_is_named_with_its_number_and_text_not_skipped(tmp_path):
    path = str(tmp_path / "findings.jsonl")
    open(path, "w").write('{"a": 1}\n\nnot json\n[1, 2]\n"str"\n{"b": 2}\n')
    log = findings_log.read(path)
    assert log.rows == [{"a": 1}, {"b": 2}]
    # line 3 is not JSON; lines 4 and 5 parse but are not objects
    assert log.corrupt == [(3, "not json"), (4, "[1, 2]"), (5, '"str"')]


def test_tally_reads_the_first_counted_row():
    rows = [{"extra": {}}, {"extra": {"killed_count": 8, "survived_count": 2, "no_coverage_count": 3}},
            {"extra": {"killed_count": 1, "survived_count": 1, "no_coverage_count": 1}}]
    assert findings_log.tally(rows) == (8, 13, 2, 3)


def test_tally_is_none_when_no_row_carries_all_three_counts():
    assert findings_log.tally([]) is None
    assert findings_log.tally([{"extra": {"killed_count": 1}}, {"extra": None}, {}]) is None
