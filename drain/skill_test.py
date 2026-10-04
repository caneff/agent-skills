#!/usr/bin/env python3
"""Tests for `drain/SKILL.md` (#1427): the `/drain` slash command stays thin.
It is prose, so the checks are the parts a reader can break mechanically: the
frontmatter that makes it user-typed only, every flag it passes through being
a flag `drain.py` accepts, the two commands it composes existing, and its
refusal of a linked worktree being the one `burndown/loop.py seat` gives.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(HERE, "SKILL.md")
DRAIN = os.path.join(HERE, "drain.py")
PASS_THROUGH = ["--once", "--max", "--anchor", "--bundle-max", "--repo"]


def skill_text():
    with open(SKILL) as handle:
        return handle.read()


class FrontmatterTest(unittest.TestCase):
    def frontmatter(self):
        match = re.match(r"---\n(.*?)\n---\n", skill_text(), re.S)
        self.assertIsNotNone(match, "SKILL.md must open with frontmatter")
        return dict(line.split(": ", 1) for line in match.group(1).splitlines())

    def test_user_typed_only_and_named_drain(self):
        fields = self.frontmatter()
        self.assertEqual(fields.get("name"), "drain")
        self.assertEqual(fields.get("disable-model-invocation"), "true")

    def test_description_is_not_parked(self):
        self.assertFalse(self.frontmatter()["description"].strip('"').startswith("Parked: "))


class PassThroughTest(unittest.TestCase):
    def test_every_flag_it_passes_is_named(self):
        text = skill_text()
        for flag in PASS_THROUGH:
            self.assertRegex(text, rf"(?<![\w-]){flag}\b", f"the skill must name {flag}")

    def test_every_flag_it_names_is_one_drain_accepts(self):
        helped = subprocess.run([sys.executable, DRAIN, "--help"], capture_output=True, text=True)
        self.assertEqual(helped.returncode, 0, helped.stderr)
        # the usage span and the `drain` command line; `job-run`'s own flags are not drain's
        spans = [re.search(r"`/drain [^`]*`", skill_text()), re.search(r"-- drain [^\n]*", skill_text())]
        self.assertNotIn(None, spans, "the usage span or the drain command line is missing")
        named = {flag for span in spans for flag in re.findall(r"--[a-z][a-z-]*", span.group(0))}
        self.assertTrue(named, "no flag found in the skill: the pattern matched nothing")
        for flag in named:
            self.assertIn(flag, helped.stdout, f"{flag} is not a drain.py flag")


class CompositionTest(unittest.TestCase):
    def test_runs_under_job_run_in_the_background(self):
        text = skill_text()
        self.assertIn("job-run --name", text)
        self.assertIn("run_in_background", text)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "flow", "bin", "job-run")))

    def test_refuses_a_linked_worktree_by_comparing_git_dirs(self):
        text = skill_text()
        self.assertIn("rev-parse --absolute-git-dir", text)
        self.assertIn("--git-common-dir", text)

    def test_names_the_run_after_the_primary_checkout(self):
        self.assertIn("never `<dir>`'s", skill_text())

    def test_separates_a_refused_start_from_a_crash(self):
        text = skill_text()
        self.assertIn("job-run --status drain-<repo-short>", text)
        self.assertIn("already live", text)

    def test_points_at_drain_py_and_names_the_pane(self):
        text = skill_text()
        self.assertIn("drain/drain.py", text)
        self.assertIn("<repo-short>-<anchor>", text)

    def test_stays_thin(self):
        self.assertLess(len(skill_text().split()), 450)


if __name__ == "__main__":
    unittest.main()
