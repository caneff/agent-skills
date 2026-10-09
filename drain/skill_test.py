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

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")
DRAIN = os.path.join(HERE, "drain.py")


def skill_text():
    with open(SKILL) as handle:
        return handle.read()


@pytest.fixture
def frontmatter():
    match = re.match(r"---\n(.*?)\n---\n", skill_text(), re.S)
    assert match is not None, "SKILL.md must open with frontmatter"
    return dict(line.split(": ", 1) for line in match.group(1).splitlines())


def test_user_typed_only_and_named_drain(frontmatter):
    assert frontmatter.get("name") == "drain"
    assert frontmatter.get("disable-model-invocation") == "true"


def test_description_is_not_parked(frontmatter):
    assert not frontmatter["description"].strip('"').startswith("Parked: ")


def test_every_flag_it_names_is_one_drain_accepts():
    helped = subprocess.run([sys.executable, DRAIN, "--help"], capture_output=True, text=True)
    assert helped.returncode == 0, helped.stderr
    # the usage span and the `drain` command line; `job-run`'s own flags are not drain's
    spans = [re.search(r"`/drain [^`]*`", skill_text()), re.search(r"-- drain [^\n]*", skill_text())]
    assert None not in spans, "the usage span or the drain command line is missing"
    named = {flag for span in spans for flag in re.findall(r"--[a-z][a-z-]*", span.group(0))}
    assert named, "no flag found in the skill: the pattern matched nothing"
    for flag in named:
        assert flag in helped.stdout, f"{flag} is not a drain.py flag"


@pytest.fixture
def completion():
    """The batched live run (#1392): its step sits under `## On completion`, and
    names what a session needs to do it without asking again."""
    match = re.search(r"^## On completion\n(.*)\Z", skill_text(), re.S | re.M)
    assert match is not None, "SKILL.md has no `## On completion` section"
    return match.group(1)


def test_live_run_step_reads_the_repos_declared_layer(completion):
    assert "**Live layer**" in completion, "the live-run step is missing from On completion"
    assert "AGENTS.md" in completion
    assert "§ End-to-end seam" in completion


def test_live_run_waits_for_chris_and_runs_once_on_merged_main(completion):
    step = " ".join(completion.split("**Live layer**", 1)[1].lower().split())
    for needle in ("on his go", "once on merged `main`", "owed live checks", "fix or revert ticket"):
        assert needle in step, f"the live-run step does not say {needle!r}"
