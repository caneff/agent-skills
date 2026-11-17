"""Pins two rules of implement/SKILL.md § The merge (#1898, #1903).

The rules are prose a controller follows, so the test reads the section the
rule lives in: a rule moved out of § The merge, or dropped, goes red here.
"""
import re
from pathlib import Path

SKILL = (Path(__file__).resolve().parent / "SKILL.md").read_text()


def section(heading):
    """Text of the `### <heading>` section, up to the next `##` heading."""
    match = re.search(rf"^###? {re.escape(heading)}\n(.*?)(?=^##)", SKILL, re.S | re.M)
    assert match, f"no section {heading!r} in SKILL.md"
    return match.group(1)


def paragraph(text, lead):
    """The blank-line-delimited paragraph starting at `lead`, on one line."""
    return " ".join(text.split(lead, 1)[1].split("\n\n", 1)[0].split())


def test_extra_runs_run_beside_the_selector_in_the_merge():
    merge = section("The merge")
    assert "**Extra runs**" in merge
    para = paragraph(merge, "**Extra runs**")
    assert "in addition" in para
    assert "never a replacement" in para


def test_extra_runs_run_beside_the_selector_in_the_worker_seam_run():
    step3 = SKILL.split("3. **Write the dispositions, then run the seam.**", 1)[1]
    step3 = " ".join(step3.split("#### The Codex pass", 1)[0].split())
    assert "**extra run** adds to it" in step3
    assert "in addition to the selector" in step3


def test_visual_pr_gets_a_real_page_screenshot_before_the_merge():
    merge = section("The merge")
    assert "**Visual PRs**" in merge
    para = paragraph(merge, "**Visual PRs**")
    assert "shot-scraper" in para
    assert "VISUAL-INSPECTION.md" in para
    assert "screenshot" in para
