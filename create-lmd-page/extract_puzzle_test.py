"""Tests for extract_puzzle (#1744; were its `--selfcheck`, which never ran).

`layout_hint` and `main` had no coverage; `main` runs here with the network and
`lzstring` stubbed.
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import extract_puzzle  # noqa: E402


@pytest.mark.parametrize("blob,expected", [
    ("t:'it\\'s here',x:'y'", "it's here"),  # escaped quote mid-value
    ("t:'plain',x:'y'", "plain"),            # stops at the closing quote
])
def test_field_reads_single_quoted_value(blob, expected):
    assert extract_puzzle.field(blob, "t") == expected


def test_field_missing_key_is_none():
    assert extract_puzzle.field("t:'x'", "author") is None


SHORT = "Normal sudoku rules apply.\n\nHit Counts: short clue.\n\nHit Lines: short clue."
LONG = "\n\n".join(f"Rule {i}: " + "word " * 60 for i in range(5))


@pytest.mark.parametrize("rules,expected", [(SHORT, "two"), (LONG, "one")])
def test_layout_hint(rules, expected):
    assert extract_puzzle.layout_hint(rules) == expected


class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text.encode()


def _run_main(monkeypatch, capsys, decompressed, arg="https://sudokupad.app/abc"):
    class FakeLZ:
        def decompressFromBase64(self, body):
            assert body == "BLOB"  # the "scl" tag is stripped first
            return decompressed

    monkeypatch.setitem(sys.modules, "lzstring", types.SimpleNamespace(LZString=FakeLZ))
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        return _FakeResponse("sclBLOB\n")

    monkeypatch.setattr(extract_puzzle.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["extract_puzzle.py", arg])
    extract_puzzle.main()
    return json.loads(capsys.readouterr().out), seen


def test_main_prints_fields_and_layout(monkeypatch, capsys):
    blob = json.dumps({"metadata": {"title": "T", "author": "A", "rules": SHORT, "solution": ""}})
    out, seen = _run_main(monkeypatch, capsys, blob)
    assert seen["url"] == "https://sudokupad.app/api/puzzle/abc"
    assert out == {"title": "T", "author": "A", "rules": SHORT, "solution": None, "layout": "two"}


def test_main_reads_a_legacy_blob(monkeypatch, capsys):
    out, _ = _run_main(monkeypatch, capsys, "{t:'T',author:'A',rules:'Rule: x',solution:'123'}", arg="abc")
    assert (out["title"], out["solution"]) == ("T", "123")


def test_main_exits_when_decompress_fails(monkeypatch, capsys):
    with pytest.raises(SystemExit, match="decompress failed"):
        _run_main(monkeypatch, capsys, None)


def test_main_exits_when_no_rules(monkeypatch, capsys):
    with pytest.raises(SystemExit, match="no rules"):
        _run_main(monkeypatch, capsys, json.dumps({"metadata": {"title": "T"}}))


def test_main_usage(monkeypatch):
    monkeypatch.setitem(sys.modules, "lzstring", types.SimpleNamespace(LZString=object))
    monkeypatch.setattr(sys, "argv", ["extract_puzzle.py"])
    with pytest.raises(SystemExit, match="usage"):
        extract_puzzle.main()
