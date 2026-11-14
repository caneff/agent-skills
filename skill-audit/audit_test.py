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


# --- CLI over a temp skills dir (#1745) -------------------------------------

def _make_skill(skills_dir, name, *, slash_only=False, frontmatter_name=True):
    d = skills_dir / name
    d.mkdir()
    lines = ["---"]
    if frontmatter_name:
        lines.append(f"name: {name}")
    lines.append("description: d")
    if slash_only:
        lines.append("disable-model-invocation: true")
    lines += ["---", "body", ""]
    (d / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return d / "SKILL.md"


def _log_line(skill, ts):
    return f'{{"skill":"{skill}","timestamp":"{ts}"}}\n'


@pytest.fixture
def env(tmp_path, monkeypatch):
    import audit
    skills = tmp_path / "skills"
    skills.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(audit, "SKILLS_DIR", str(skills))
    monkeypatch.setattr(audit, "LOGS", str(logs / "**" / "*.jsonl"))
    return skills, logs


def test_cli_report_lists_stale_model_invocable_skills(env, capsys):
    import audit
    skills, logs = env
    _make_skill(skills, "never-used")
    _make_skill(skills, "old")
    _make_skill(skills, "fresh")
    _make_skill(skills, "manual", slash_only=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (logs / "a.jsonl").write_text(
        _log_line("old", "2020-01-01T00:00:00Z") + _log_line("old", "2020-01-02T00:00:00Z")
        + _log_line("fresh", now) + _log_line("unknown-skill", now)
        + "no skill here\n"
        + '{"skill":"fresh"}\n'              # no timestamp: ignored
        + _log_line("manual", "not-a-date"),  # bad timestamp: ignored
        encoding="utf-8")
    assert audit.main([]) == 0
    out = capsys.readouterr().out
    assert "Skills in" in out and ": 4  |  model-invocable (cost context): 3" in out
    assert "Stale threshold: >45 days" in out
    assert "2 model-invocable skill(s) unused >45d" in out
    assert "last used 2020-01-02" in out          # latest timestamp wins
    assert "last used NEVER" in out
    assert "fresh" in out.split("2 model-invocable")[0]
    assert "fresh" not in out.split("2 model-invocable")[1].split("To flip")[0]
    assert "slash-only" in out
    # model-invocable rows come before slash-only; never-used before older
    table = out.split("-" * 62)[1].split("2 model-invocable")[0]
    order = [ln.split()[0] for ln in table.strip().splitlines()]
    assert order == ["never-used", "old", "fresh", "manual"]
    assert "To flip: uv run --no-project python" in out and "--flip <nums>" in out
    assert " 45 --flip" not in out


def test_cli_custom_stale_days_shows_in_flip_hint(env, capsys):
    import audit
    skills, _ = env
    _make_skill(skills, "x")
    audit.main(["10"])
    out = capsys.readouterr().out
    assert "Stale threshold: >10 days" in out and " 10 --flip <nums>" in out


def test_cli_uses_directory_name_without_frontmatter_name(env, capsys):
    import audit
    skills, _ = env
    _make_skill(skills, "dirname", frontmatter_name=False)
    audit.main([])
    assert "dirname" in capsys.readouterr().out


def test_cli_flip_flips_picked_numbers_and_reports_the_rest(env, capsys):
    import audit
    skills, _ = env
    a = _make_skill(skills, "a")
    b = _make_skill(skills, "b")
    assert audit.main(["--flip", "1,9"]) == 0
    out = capsys.readouterr().out
    assert "9: out of range (1–2) — skipped" in out
    assert "1. a: flipped to slash-only" in out or "1. b: flipped to slash-only" in out
    flipped = [p for p in (a, b) if "disable-model-invocation" in p.read_text(encoding="utf-8")]
    assert len(flipped) == 1
    assert "Re-run without --flip to see the updated report." in out


def test_cli_flip_twice_says_already_slash_only(env, capsys):
    import audit
    skills, logs = env
    _make_skill(skills, "only")
    audit.main(["--flip", "1"])
    capsys.readouterr()
    # after flipping it is no longer stale, so list is empty → out of range
    audit.main(["--flip", "1"])
    assert "out of range (1–0)" in capsys.readouterr().out


def test_build_rows_orders_never_used_then_oldest_then_slash_only():
    import audit
    # insertion order is the reverse of the expected order, so a missing sort fails
    model_inv = {"manual": False, "recent": True, "old": True, "never": True}
    paths = {n: f"/{n}" for n in model_inv}
    last = {"recent": datetime(2020, 2, 28, tzinfo=timezone.utc),
            "old": datetime(2020, 1, 1, tzinfo=timezone.utc)}
    rows = audit.build_rows(paths, model_inv, last, NOW, 45)
    assert [r.name for r in rows] == ["never", "old", "recent", "manual"]
