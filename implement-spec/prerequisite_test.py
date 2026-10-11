"""The spec run's prerequisite is stated before its first step (#1532).

`implement-dispatch --spec` refuses a spec with no sub-issues, but a
controller that enters the skill without that command is stopped only if
the skill itself names `/to-tickets`.
"""
import os
import re

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")


def first_section():
    text = open(SKILL).read()
    # Drop the frontmatter, then take everything up to the second heading.
    body = text.split("---", 2)[2]
    parts = re.split(r"^## ", body, flags=re.M)
    return parts[1]


def test_first_section_names_to_tickets_as_the_prerequisite():
    section = first_section()
    assert "/to-tickets" in section, section[:200]
    assert "sub-issue" in section, section[:200]
