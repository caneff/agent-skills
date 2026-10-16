"""The spec run's fix round runs the repo's per-change command (#1602).

`implement-spec/SKILL.md` § The integration branch step 3 runs what
`selector_check.py command` prints, as `implement/SKILL.md` § Review step 3
does (#1593). The nightly backstop is the only full run (#1592), so the step
names no `tests/all.sh`.

Seam: the Markdown text of that step.
"""
from pathlib import Path

SKILL = Path(__file__).with_name("SKILL.md")


def fix_round_step():
    text = " ".join(SKILL.read_text().split())
    start = text.index("3. **One fix round.**")
    return text[start:text.index("4. **The integration PR.**")]


def test_fix_round_runs_the_resolver_output():
    assert "selector_check.py command" in fix_round_step()


def test_fix_round_names_no_hard_coded_seam():
    assert "tests/all.sh" not in fix_round_step()
