"""Fixture for the `prose-assertion` category (answer-key rows 11-12)."""
from pathlib import Path

from pricing import apply_discount

SKILL = Path(__file__).parent / "SKILL.md"


def test_skill_says_discounts_are_capped():
    # Only assertion: the prose file contains a sentence.
    assert "discounts are capped at 100%" in SKILL.read_text()


def test_discount_over_100_percent_is_capped():
    # Runs the code under test; reads no prose.
    assert apply_discount(100, 150) == 0
