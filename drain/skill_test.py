#!/usr/bin/env python3
"""Tests for `drain/SKILL.md` (#1427). Two things a machine reads off it: the
frontmatter that makes it user-typed only (install and skill discovery read
those keys), and the flags it names, each checked against `drain.py --help`
so a renamed flag goes red.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")
DRAIN = os.path.join(HERE, "drain.py")


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


class LiveLayerTest(unittest.TestCase):
    """The batched live run (#1392): its step sits under `## On completion`, and
    names what a session needs to do it without asking again."""

    def completion(self):
        match = re.search(r"^## On completion\n(.*)\Z", skill_text(), re.S | re.M)
        self.assertIsNotNone(match, "SKILL.md has no `## On completion` section")
        return match.group(1)

    def test_live_run_step_reads_the_repos_declared_layer(self):
        text = self.completion()
        self.assertIn("**Live layer**", text, "the live-run step is missing from On completion")
        self.assertIn("AGENTS.md", text)
        self.assertIn("§ End-to-end seam", text)

    def test_live_run_waits_for_chris_and_runs_once_on_merged_main(self):
        step = " ".join(self.completion().split("**Live layer**", 1)[1].lower().split())
        for needle in ("on his go", "once on merged `main`", "owed live checks", "fix or revert ticket"):
            self.assertIn(needle, step, f"the live-run step does not say {needle!r}")


if __name__ == "__main__":
    unittest.main()
