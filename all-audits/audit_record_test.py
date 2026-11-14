"""Tests for `audit_record`: the HTML heading parser and the rendered findings."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import audit_record  # noqa: E402


def _model(**kw):
    base = dict(sweep_id="s", timestamp="t", sha="abc", clean="yes", stored_path="p", ran=["x"], skipped={},
                failed={}, findings={}, no_log={}, suppressed=0, suppression_unreported=[], headings={}, synthesis="")
    return audit_record.RecordModel(**{**base, **kw})


def test_report_headings_takes_h1_to_h3_in_order_with_whitespace_collapsed():
    html_text = "<h1>Top\n  level</h1><p>x</p><h2>Second <em>one</em></h2><h3>Third</h3><h4>no</h4>"
    assert audit_record.report_headings(html_text) == ["Top level", "Second one", "Third"]


def test_report_headings_skips_an_empty_heading_and_text_outside_headings():
    assert audit_record.report_headings("<h2>  </h2><p>body</p><h2></h2>") == []
    assert audit_record.report_headings("") == []


def test_report_headings_closes_a_heading_at_its_end_tag_only():
    assert audit_record.report_headings("<h2>a</h2>stray<h3>b</h3>") == ["a", "b"]


def test_build_renders_a_corrupt_line_string_verbatim():
    body = audit_record.build(_model(findings={"x": ["line 3: not json"]}))[0]
    assert "unparseable line in findings.jsonl, kept verbatim: `line 3: not json`" in body


def test_build_renders_a_finding_row():
    row = {"file": "a.py", "line": 3, "summary": "bad", "failure": "breaks", "after": "fix", "bucket": "b", "category": "c"}
    body = audit_record.build(_model(findings={"x": [row]}))[0]
    assert "- `a.py:3` — bad [b/c]" in body and "Problem: breaks" in body and "Suggestion: fix" in body
