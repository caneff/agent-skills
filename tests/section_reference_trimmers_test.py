"""Pins the label trimmers of check-section-references.py: which run, in what order."""
import importlib.util
import re
from pathlib import Path

import pytest


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location(
        "checker", Path(__file__).with_name("check-section-references.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trimmers_run_in_order(checker):
    assert [name for name, _ in checker.PROSE_TRIMMERS] == [
        "cross-reference conjunction",
        "trailing conjunction",
        "possessive",
    ]
    assert checker.PUNCTUATION_TRIMMER[0] == "sentence punctuation"


def test_a_trimmer_added_to_prose_trimmers_runs(checker, monkeypatch):
    monkeypatch.setattr(
        checker,
        "PROSE_TRIMMERS",
        checker.PROSE_TRIMMERS + (("footnote", lambda v: v.split(" [^", 1)[0]),),
    )
    match = re.search(checker.SECTION, "See § Alpha [^1] for details")
    assert ("Alpha", []) in checker.reference_targets(match)


def test_step_locator_is_read_before_punctuation_cuts_the_label(checker):
    match = re.search(checker.SECTION, "See § Before the PR: step 5 for details.")
    assert ("Before the PR", [5]) in checker.reference_targets(match)
