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
import tempfile
import unittest
from pathlib import Path

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


class RealTree(unittest.TestCase):
    def test_real_claude_md_is_within_budget(self):
        code, out = run(REAL)
        print(out, end="")
        self.assertEqual(code, 0, out)
        self.assertIn("within budget", out)


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        (self.home / "mem").mkdir(parents=True)
        (self.home / "mem" / "A.md").write_text("one two three\n")
        self.root = self.tmp / "repo"
        (self.root / "flow" / "claude").mkdir(parents=True)
        (self.root / "flow" / "claude" / "WORKFLOW.md").write_text("# w\n")

    def write(self, text: str) -> Path:
        f = self.root / "flow" / "claude" / "CLAUDE.md"
        f.write_text(text)
        return f

    def check(self, text: str):
        return run(self.write(text), self.root, str(self.home))

    def test_imports_are_counted(self):
        code, out = self.check("alpha beta\n@~/mem/A.md\n")
        self.assertEqual(code, 0, out)
        # 3 words in CLAUDE.md (the import line is one) + 3 imported.
        self.assertIn("total 6 words", out)

    def test_nested_import_is_counted(self):
        (self.home / "mem" / "A.md").write_text("one @~/mem/B.md\n")
        (self.home / "mem" / "B.md").write_text("x y z w\n")
        code, out = self.check("@~/mem/A.md\n")
        self.assertEqual(code, 0, out)
        self.assertIn("total 7 words", out)

    def test_missing_import_fails(self):
        # An import that cannot be read must not count as zero words.
        code, out = self.check("@~/mem/Gone.md\n")
        self.assertNotEqual(code, 0, out)
        self.assertIn("import not found: ~/mem/Gone.md", out)

    def test_dead_pointer_fails(self):
        code, out = self.check(
            "- Before you land work: read `~/.agents/skills/flow/claude/NOPE.md`.\n")
        self.assertNotEqual(code, 0, out)
        self.assertIn("names a path that does not exist: ~/.agents/skills/flow/claude/NOPE.md", out)

    def test_live_pointer_maps_into_the_checkout(self):
        # ~/.agents/skills/ is this repo: a pointer resolves into the checkout
        # under test, so a doc a branch adds is found before it merges.
        code, out = self.check(
            "- Before you land work: read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
        self.assertEqual(code, 0, out)

    def test_wrapped_pointer_is_read_as_one_line(self):
        code, out = self.check(
            "- Before you land work:\n  read `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
        self.assertEqual(code, 0, out)

    def test_pointer_without_an_action_fails(self):
        code, out = self.check("Detail: `~/.agents/skills/flow/claude/WORKFLOW.md`.\n")
        self.assertNotEqual(code, 0, out)
        self.assertIn("pointer line names no action", out)

    def test_real_claude_md_plus_200_words_fails_on_budget(self):
        text = REAL.read_text() + "\n" + " ".join(["word"] * 200) + "\n"
        f = self.tmp / "CLAUDE.md"
        f.write_text(text)
        code, out = run(f)
        self.assertNotEqual(code, 0, out)
        self.assertIn("over budget", out)
        self.assertNotIn("does not exist", out)
        self.assertNotIn("import not found", out)


if __name__ == "__main__":
    unittest.main()
