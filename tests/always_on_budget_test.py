#!/usr/bin/env python3
"""The always-on budget gate (#1413): every session loads the global
CLAUDE.md plus its `@`-imports, and tests/check-always-on.py fails when that
text passes its word budget or a pointer line names a path that does not
exist. Each case runs the checker's command line and reads its exit status
and output; the real-tree case is the gate itself, the rest are fixtures
that prove each failure is caught by its own assertion."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "tests" / "check-always-on.py"
REAL = ROOT / "flow" / "claude" / "CLAUDE.md"


def run(claude_md: Path, root: Path = ROOT, home: str | None = None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    p = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), str(claude_md)],
        capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def test_real_claude_md_is_within_budget():
    code, out = run(REAL)
    print(out, end="")
    assert code == 0, out
    assert "within budget" in out


class Fixtures:
    """A scratch repo with a CLAUDE.md under test and a home holding its imports."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.home = tmp / "home"
        (self.home / "mem").mkdir(parents=True)
        (self.home / "mem" / "A.md").write_text("one two three\n")
        self.root = tmp / "repo"
        (self.root / "flow" / "claude").mkdir(parents=True)
        (self.root / "flow" / "claude" / "WORKFLOW.md").write_text("# w\n")

    def write(self, text: str) -> Path:
        f = self.root / "flow" / "claude" / "CLAUDE.md"
        f.write_text(text)
        return f

    def check(self, text: str):
        return run(self.write(text), self.root, str(self.home))


@pytest.fixture
def fx(tmp_path):
    return Fixtures(tmp_path)


def test_imports_are_counted(fx):
    code, out = fx.check("alpha beta\n@~/mem/A.md\n")
    assert code == 0, out
    # 3 words in CLAUDE.md (the import line is one) + 3 imported.
    assert "total 6 words" in out


def test_nested_import_is_counted(fx):
    (fx.home / "mem" / "A.md").write_text("one @~/mem/B.md\n")
    (fx.home / "mem" / "B.md").write_text("x y z w\n")
    code, out = fx.check("@~/mem/A.md\n")
    assert code == 0, out
    assert "total 7 words" in out


def test_missing_import_fails(fx):
    # An import that cannot be read must not count as zero words.
    code, out = fx.check("@~/mem/Gone.md\n")
    assert code != 0, out
    assert "import not found: ~/mem/Gone.md" in out


def test_dead_pointer_fails(fx):
    code, out = fx.check(
        "- Before you land work: read `~/.agents/skills/flow/claude/NOPE.md`.\n")
    assert code != 0, out
    assert "names a path that does not exist: ~/.agents/skills/flow/claude/NOPE.md" in out


def test_live_pointer_maps_into_the_checkout(fx):
    # ~/.agents/skills/ is this repo: a pointer resolves into the checkout
    # under test, so a doc a branch adds is found before it merges.
    code, out = fx.check(
        "- Before you land work: read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code == 0, out


def test_wrapped_pointer_is_read_as_one_line(fx):
    code, out = fx.check(
        "- Before you land work:\n  read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code == 0, out


def test_pointer_without_an_action_fails(fx):
    code, out = fx.check("Detail: `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
    assert code != 0, out
    assert "pointer line names no action" in out


def test_real_claude_md_plus_200_words_fails_on_budget(fx):
    text = REAL.read_text() + "\n" + " ".join(["word"] * 200) + "\n"
    f = fx.tmp / "CLAUDE.md"
    f.write_text(text)
    code, out = run(f)
    assert code != 0, out
    assert "over budget" in out
    assert "does not exist" not in out
    assert "import not found" not in out

