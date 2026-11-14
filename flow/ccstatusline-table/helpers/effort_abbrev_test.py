"""effort-abbrev.py: `get_level` source order and the rendered cell (#1753)."""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "effort-abbrev.py"
spec = importlib.util.spec_from_file_location("effort_abbrev", SCRIPT)
ea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ea)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    return tmp_path


def stdin(monkeypatch, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_get_level_prefers_stdin(home, monkeypatch):
    (home / ".claude/settings.json").write_text(json.dumps({"effortLevel": "low"}))
    stdin(monkeypatch, json.dumps({"effort": {"level": "high"}}))
    assert ea.get_level() == "high"


def test_get_level_falls_back_to_settings(home, monkeypatch):
    (home / ".claude/settings.json").write_text(json.dumps({"effortLevel": "low"}))
    stdin(monkeypatch, "{}")
    assert ea.get_level() == "low"


def test_get_level_bad_stdin_uses_settings(home, monkeypatch):
    (home / ".claude/settings.json").write_text(json.dumps({"effortLevel": "max"}))
    stdin(monkeypatch, "not json")
    assert ea.get_level() == "max"


def test_get_level_none_without_either_source(home, monkeypatch):
    stdin(monkeypatch, "{}")
    assert ea.get_level() is None


def test_get_level_unreadable_settings_is_none(home, monkeypatch):
    (home / ".claude/settings.json").write_text("not json")
    stdin(monkeypatch, "{}")
    assert ea.get_level() is None


@pytest.mark.parametrize("level,cell", [
    ("low", "(L)"), ("medium", "(M)"), ("high", "(H)"), ("xhigh", "(XH)"),
    ("MAX", "(MAX)"), ("turbo", "(turbo?)"),
])
def test_cell_as_process(home, level, cell):
    p = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps({"effort": {"level": level}}),
                       capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin"})
    assert p.stdout == cell


def test_cell_blank_without_level(home):
    p = subprocess.run([sys.executable, str(SCRIPT)], input="{}", capture_output=True, text=True,
                       env={"HOME": str(home), "PATH": "/usr/bin"})
    assert p.stdout == ""


def test_stdin_parse_does_not_swallow_programming_errors(home, monkeypatch):
    stdin(monkeypatch, "{}")
    monkeypatch.setattr(ea.json, "load", lambda f: (_ for _ in ()).throw(TypeError("bug")))
    with pytest.raises(TypeError):
        ea.get_level()


def test_settings_read_does_not_swallow_programming_errors(home, monkeypatch):
    (home / ".claude/settings.json").write_text(json.dumps({"effortLevel": "low"}))
    stdin(monkeypatch, "{}")
    real = json.load

    def load(f):
        if f is sys.stdin:
            return real(f)
        raise TypeError("bug")

    monkeypatch.setattr(ea.json, "load", load)
    with pytest.raises(TypeError):
        ea.get_level()


def test_get_level_settings_not_an_object_is_none(home, monkeypatch):
    (home / ".claude/settings.json").write_text("[1]")
    stdin(monkeypatch, "{}")
    assert ea.get_level() is None
