"""One-function tests for the ledger's harvest and transcript readers (#1776, spec #1735).
Each test drives one function directly; the output pin (`review_ledger_report_pin_test.py`)
covers the whole report."""
import importlib.util
import json
import sys

from review_ledger_support import SCRIPT, finding, write_jsonl

_spec = importlib.util.spec_from_file_location("review_ledger_under_test", SCRIPT)
rl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rl
_spec.loader.exec_module(rl)


def test_first_text_returns_a_string_content_as_is():
    assert rl._first_text({"message": {"content": "hello"}}) == "hello"


def test_first_text_joins_the_text_of_each_block_and_skips_non_dict_blocks():
    obj = {"message": {"content": [{"type": "text", "text": "a"}, "junk", {"type": "image"}, {"text": "b"}]}}
    assert rl._first_text(obj) == "a  b"


def test_first_text_is_none_when_the_message_or_its_content_is_unusable():
    assert rl._first_text({"message": "not a dict"}) is None
    assert rl._first_text({"message": {"content": 5}}) is None
    assert rl._first_text({}) is None


def test_harvest_findings_file_makes_one_row_joined_to_its_disposition(tmp_path):
    cache = tmp_path / "cache"
    write_jsonl(cache / "skills" / "findings-standards-100.jsonl", [finding("S1", "hard", "a.py", "Dup")])
    write_jsonl(cache / "skills" / "dispositions-100.jsonl", [{"id": "S1", "outcome": "fixed", "sha": "abc1234"}])
    rows, facts = rl.harvest_cache(cache, None, missing="no transcripts here")
    standards = [r for r in rows if r["type"] == "standards"]
    assert len(standards) == 1
    (f,) = standards[0]["findings"]
    assert (f["id"], f["outcome"]) == ("S1", "fixed")
    assert facts["orphans"] == []


def test_a_disposition_with_no_finding_is_an_orphan(tmp_path):
    cache = tmp_path / "cache"
    write_jsonl(cache / "skills" / "findings-standards-100.jsonl", [finding("S1", "hard", "a.py", "Dup")])
    write_jsonl(cache / "skills" / "dispositions-100.jsonl", [
        {"id": "S1", "outcome": "fixed", "sha": "abc1234"}, {"id": "S9", "outcome": "fixed", "sha": "abc1234"}])
    _, facts = rl.harvest_cache(cache, None, missing="no transcripts here")
    assert len(facts["orphans"]) == 1 and "S9" in facts["orphans"][0]


def test_read_transcript_reports_unknown_tokens_for_an_unreadable_line(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("not json\n" + json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z",
                                            "message": {"content": "hi"}}) + "\n")
    t = rl.read_transcript(p)
    assert t["first"] == "hi"
    assert t["tokens"]["status"] == "unknown" and "unreadable" in t["tokens"]["reason"]
    assert t["wall_clock"]["status"] == "unknown"
