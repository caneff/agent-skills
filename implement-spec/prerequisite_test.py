"""The spec run's prerequisite is stated before its first step (#1532).

`implement-dispatch --spec` refuses a spec with no sub-issues, but a
controller that enters the skill without that command is stopped only if
the skill itself names `/to-tickets`.
"""
import re
from pathlib import Path

SKILL = Path(__file__).with_name("SKILL.md")


def test_first_section_names_to_tickets_as_the_prerequisite():
    match = re.search(r"^## (.*?)(?=^## )", SKILL.read_text(), re.M | re.S)
    assert match, "SKILL.md has no second '## ' heading to end the first section"
    section = match.group(1)
    assert "/to-tickets" in section, section[:200]
    assert "sub-issue" in section, section[:200]
