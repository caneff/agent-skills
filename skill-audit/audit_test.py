"""Tests for skill-audit's frontmatter helpers (#1744; was `audit.py`'s `_selfcheck`)."""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from audit import Skill, add_flag, flip_skill, parse_frontmatter  # noqa: E402

SRC = "---\nname: foo\ndescription: bar\n---\nbody\n"


def test_parse_frontmatter_keeps_later_colons():
    fm = parse_frontmatter("---\nname: grill\ndescription: Use when they say: stop.\n---\nbody\n")
    assert fm == {"name": "grill", "description": "Use when they say: stop."}


def test_add_flag_inserts_after_the_opening_fence_once():
    out, changed = add_flag(SRC)
    assert changed
    assert out.index("disable-model-invocation: true") < out.index("name: foo") < out.index("description")
    assert out.count("disable-model-invocation") == 1


def test_add_flag_is_idempotent():
    out, _ = add_flag(SRC)
    out2, changed2 = add_flag(out)
    assert not changed2 and out2 == out


def test_add_flag_without_frontmatter_raises():
    with pytest.raises(ValueError):
        add_flag("no fence here\n")


def test_flip_skill_writes_once(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text(SRC, encoding="utf-8")
    assert flip_skill(str(path)) is True
    assert "disable-model-invocation: true" in path.read_text(encoding="utf-8")
    assert flip_skill(str(path)) is False


NOW = datetime(2020, 3, 1, tzinfo=timezone.utc)
USED = datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("model_invocable,last_used,age,stale", [
    (True, USED, 60, True),     # older than the 45-day threshold
    (False, USED, 60, False),   # not model-invocable: never stale
    (True, None, None, True),   # never used
    (True, NOW, 0, False),      # used today
])
def test_skill_make_staleness(model_invocable, last_used, age, stale):
    skill = Skill.make("s", "/x", model_invocable, last_used, NOW, 45)
    assert (skill.age_days, skill.stale) == (age, stale)
