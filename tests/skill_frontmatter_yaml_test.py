# all.sh: prose-check (reads the tree's Markdown: a Markdown-only change in a directory with no suites runs it)
"""#2024, #2027: `npx skills update -g` parses each SKILL.md frontmatter as
strict YAML and skips a skill it cannot parse. An unquoted `description:` that
holds a `: ` reads as a nested mapping and the skill silently stops updating
(create-lmd-page did). The real-tree case loads every tracked SKILL.md's
frontmatter with PyYAML's safe loader (pinned in pyproject.toml's dev group)
and fails on one that does not parse to a mapping with a non-empty string
`name` and `description`; a duplicate key fails too, as in npm `yaml`. The
other cases feed `problems` fixtures, so each failure is caught by its own
assertion."""
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


class Strict(yaml.SafeLoader):
    pass


def _no_dup(loader, node, deep=False):
    seen = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=True)
        if key in seen:
            raise yaml.YAMLError(f"duplicate key {key!r} (npm yaml rejects it, PyYAML keeps the last)")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)


def problems(text: str) -> list[str]:
    """What is wrong with one SKILL.md's frontmatter; empty when it is sound."""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return ["has no ---/--- frontmatter block"]
    block = "\n".join(lines[1 : lines.index("---", 1)])
    try:
        data = yaml.load(block, Loader=Strict)
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML: {str(e)!r}"]
    if not isinstance(data, dict):
        return ["frontmatter is not a mapping"]
    return [f"frontmatter `{k}` is not a non-empty string"
            for k in ("name", "description")
            if not isinstance(data.get(k), str) or not data[k].strip()]


def tracked_skill_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", "SKILL.md", "*/SKILL.md"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0") if f]


def test_every_tracked_skill_md_parses_as_strict_yaml():
    files = tracked_skill_files()
    assert files, "no tracked SKILL.md found, so nothing was parsed"
    bad = [f"{f}: {p}" for f in files
           for p in problems((ROOT / f).read_text(encoding="utf-8"))]
    assert not bad, "\n".join(bad)


GOOD = "---\nname: x\ndescription: 'Does a thing: well'\n---\nbody\n"


def test_sound_frontmatter_has_no_problems():
    assert problems(GOOD) == []


@pytest.mark.parametrize("text, needle", [
    ("---\nname: x\ndescription: Does a thing: well\n---\n", "not valid YAML"),
    ("---\nname: x\nname: y\ndescription: d\n---\n", "duplicate key 'name'"),
    ("no frontmatter\n", "no ---/--- frontmatter block"),
    ("---\n- a\n- b\n---\n", "not a mapping"),
    ("---\nname: x\n---\n", "`description` is not a non-empty string"),
    ("---\nname: 12\ndescription: d\n---\n", "`name` is not a non-empty string"),
])
def test_each_malformed_frontmatter_is_reported(text, needle):
    assert any(needle in p for p in problems(text)), problems(text)
