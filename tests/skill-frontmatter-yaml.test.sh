#!/usr/bin/env bash
# #2024: `npx skills update -g` parses each SKILL.md frontmatter as strict YAML
# and skips a skill it cannot parse. An unquoted `description:` that holds a
# `: ` reads as a nested mapping and the skill silently stops updating
# (create-lmd-page did). Loads every tracked SKILL.md's frontmatter with
# PyYAML's safe loader and fails on one that does not parse to a mapping with a
# string `name` and `description`; a duplicate key fails too, as in npm `yaml`. PyYAML is the system python3's, not a locked
# test tool; a box without it fails here, never skips.
# all.sh: prose-check (reads the tree's Markdown: a Markdown-only change in a directory with no suites runs it)
set -u
root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1
git ls-files -z -- 'SKILL.md' '*/SKILL.md' | python3 -I -c '
import sys
try:
    import yaml
except ImportError as e:
    print("FAIL: PyYAML is not importable by system python3 (%s); nothing was checked" % e)
    sys.exit(1)
class Strict(yaml.SafeLoader):
    pass
def no_dup(loader, node, deep=False):
    seen = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=True)
        if key in seen:
            raise yaml.YAMLError("duplicate key %r (npm yaml rejects it, PyYAML keeps the last)" % (key,))
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)
Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dup)
files = [f for f in sys.stdin.buffer.read().decode().split("\0") if f]
if not files:
    print("FAIL: no tracked SKILL.md found, so nothing was parsed")
    sys.exit(1)
bad = 0
for f in files:
    lines = open(f, encoding="utf-8").read().split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        print("FAIL: %s has no ---/--- frontmatter block" % f)
        bad += 1
        continue
    block = "\n".join(lines[1 : lines.index("---", 1)])
    try:
        data = yaml.load(block, Loader=Strict)
    except yaml.YAMLError as e:
        print("FAIL: %s frontmatter is not valid YAML: %s" % (f, str(e).replace("\n", " ")))
        bad += 1
        continue
    if not isinstance(data, dict):
        print("FAIL: %s frontmatter is not a mapping" % f)
        bad += 1
        continue
    for k in ("name", "description"):
        if not isinstance(data.get(k), str) or not data[k].strip():
            print("FAIL: %s frontmatter `%s` is not a non-empty string" % (f, k))
            bad += 1
if bad:
    sys.exit(1)
print("ok: %d SKILL.md frontmatters parse as strict YAML" % len(files))
'
