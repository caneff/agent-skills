#!/usr/bin/env python3
"""Structure test for the create-lmd-page closing step (#1288): the archive
step exists, passes --slug on every call, asks for the LMD id, allows a skip
naming the backfill fallback, and reports a failed archive.

Blind to: whether a model follows the prose, and the `lmd_archive` command
itself (tested in sudokupad-art#261, #262, #287).
"""
import re
import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent / "SKILL.md").read_text()


def closing_step():
    m = re.search(r"^## Archive\n(.*?)(?=^## |\Z)", SKILL, re.S | re.M)
    assert m, "SKILL.md has no '## Archive' section"
    return m.group(1)


def archive_commands(text):
    return [l for l in text.splitlines() if "lmd_archive" in l and " archive " in l]


class ClosingStepTest(unittest.TestCase):
    def test_runs_after_clipboard_step(self):
        self.assertLess(SKILL.index("## Output"), SKILL.index("## Archive"))

    def test_first_call_passes_link_and_slug(self):
        cmds = [c for c in archive_commands(closing_step()) if "--lmd" not in c]
        self.assertEqual(len(cmds), 1, cmds)
        self.assertIn("--slug", cmds[0])
        self.assertIn("<sudokupad-link>", cmds[0])

    def test_rerun_passes_lmd_and_slug(self):
        cmds = [c for c in archive_commands(closing_step()) if "--lmd" in c]
        self.assertEqual(len(cmds), 1, cmds)
        self.assertIn("--slug", cmds[0])

    def test_uses_absolute_repo_path_and_archive_clone(self):
        for c in archive_commands(closing_step()):
            self.assertIn("~/src/sudokupad-art", c)
            self.assertIn("--archive ~/src/lmd-archive", c)

    def test_link_is_the_page_link_verbatim(self):
        self.assertRegex(closing_step(), r"verbatim|exactly as the page uses")

    def test_skip_names_backfill_fallback(self):
        t = closing_step()
        self.assertIn("backfill", t)
        self.assertRegex(t, r"skip")
        self.assertIn("SudokuPad link", t)

    def test_failure_is_reported_not_swallowed(self):
        self.assertRegex(closing_step(), r"(?i)non-zero|exit")
        self.assertRegex(closing_step(), r"(?i)report")


if __name__ == "__main__":
    unittest.main()
