"""One-function tests for the ledger's harvest and transcript readers (#1776, spec #1735).
Each test drives one function directly; the output pin (`review_ledger_report_pin_test.py`)
covers the whole report."""
import argparse
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
    """#1735 P5: one findings file, through `_harvest_findings_file` alone."""
    cache = tmp_path / "cache"
    write_jsonl(cache / "skills" / "findings-standards-100.jsonl", [finding("S1", "hard", "a.py", "Dup")])
    state = rl._RepoHarvest({"100": {"S1": {"id": "S1", "outcome": "fixed", "sha": "abc1234"}}}, rl.HarvestFacts())
    name = "findings-standards-100.jsonl"
    rows = rl._harvest_findings_file(cache, "skills", "skills", name, rl.findings_name(name), state, set())
    assert [(r["type"], r["ticket"]) for r in rows] == [("standards", 100)]
    (f,) = rows[0]["findings"]
    assert (f["id"], f["outcome"]) == ("S1", "fixed")
    assert state.joined == {("100", "S1")}


def test_write_appended_adds_one_row_marked_as_appended(tmp_path):
    """#1735 P5: one row, through `_write_appended` alone."""
    ledger = tmp_path / "ledger.jsonl"
    row = {"row_id": "skills/100/spec/1/r", "repo": "skills", "ticket": 100, "tickets": [100], "type": "spec",
           "round": 1, "run_id": "r", "findings": [], "cost": {}, "model": None, "pr": None,
           "status": {"fields": {"findings": {"status": "known"}}, "mappings": [], "sources": []}}
    args = argparse.Namespace(ledger=ledger)
    assert rl._write_appended(args, [row]) == 0
    (written,) = rl.read_ledger(ledger)
    assert (written["row_id"], written["origin"]) == ("skills/100/spec/1/r", "append")


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
