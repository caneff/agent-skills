"""Pins two rules of implement/SKILL.md § The merge (#1898, #1903).

The rules are prose a controller follows, so the test reads the section the
rule lives in: a rule moved out of § The merge, or dropped, goes red here.
"""
import re
from pathlib import Path

SKILL = (Path(__file__).resolve().parent / "SKILL.md").read_text()


def section(heading):
    """Text of the `### <heading>` section, up to the next heading of level 2 or deeper."""
    match = re.search(rf"^###? {re.escape(heading)}\n(.*?)(?=^##)", SKILL, re.S | re.M)
    assert match, f"no section {heading!r} in SKILL.md"
    return match.group(1)


def paragraph(text, lead):
    """The blank-line-delimited paragraph starting at `lead`, on one line."""
    assert lead in text, f"no paragraph led by {lead!r}"
    return " ".join(text.split(lead, 1)[1].split("\n\n", 1)[0].split())


def test_extra_runs_run_beside_the_selector_in_the_merge():
    para = paragraph(section("The merge"), "**Extra runs**")
    assert "defined in § Review step 3" in para
    assert "never a replacement" in para
    assert "A red extra run blocks the merge" in para
    assert "never skips an extra run" in para


def test_skip_rule_covers_the_selector_run_only():
    merge = " ".join(section("The merge").split())
    assert "The skip covers the selector run only" in merge
    assert "never skips the screenshot" in merge


def test_extra_runs_run_beside_the_selector_in_the_worker_seam_run():
    step3 = SKILL.split("3. **Write the dispositions, then run the seam.**", 1)[1]
    step3 = " ".join(step3.split("#### The Codex pass", 1)[0].split())
    assert "**extra run** adds to it" in step3
    assert "in addition to the selector" in step3
    assert "each must be green" in step3


def test_visual_pr_gets_a_real_page_screenshot_before_the_merge():
    para = paragraph(section("The merge"), "**Visual PRs**")
    assert "before the merge, and the merge waits for it" in para
    assert "shot-scraper" in para
    assert "VISUAL-INSPECTION.md" in para
    assert "A regression" in para and "blocks the merge" in para
    assert "screenshot not taken: <why>" in para
    assert "never skipped silently" in para
