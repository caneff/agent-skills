#!/usr/bin/env python3
"""The dispositions sidecar fixture and the grammar SKILL.md § Review states
must agree (#1025, #1027). A reader's test that binds to the fixture is
tested on every form the prose states only while the two agree; a fixture line the prose never states is a
form no writer produces.

Seam: the sidecar forms as § Review writes them — each backticked
`{"id": ...}` object — against the lines of `fixtures/dispositions-sidecar.jsonl`,
compared by outcome and key set.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")
FIXTURE = os.path.join(HERE, "fixtures", "dispositions-sidecar.jsonl")


def review_section():
    text = open(SKILL).read()
    start = text.index("\n### Review\n")
    end = text.index("\n### Before the PR\n", start)
    return text[start:end]


def stated_forms():
    """(outcome, keys, scope) for each sidecar form § Review states. A
    placeholder written unquoted (`"ticket": <n>`) is read as a number."""
    forms = set()
    for raw in re.findall(r'`(\{"id": [^`]*\})`', review_section()):
        obj = json.loads(re.sub(r":\s*<[^>]*>", ": 0", raw))
        forms.add((obj["outcome"], frozenset(obj), obj.get("scope")))
    return forms


def fixture_forms():
    with open(FIXTURE) as fh:
        objs = [json.loads(raw) for raw in fh if raw.strip()]
    return {(o["outcome"], frozenset(o), o.get("scope")) for o in objs}


def test_every_stated_form_has_a_fixture_line():
    missing = stated_forms() - fixture_forms()
    assert not missing, f"forms § Review states with no fixture line: {missing}"


def test_every_fixture_line_is_a_stated_form():
    extra = fixture_forms() - stated_forms()
    assert not extra, f"fixture lines § Review never states: {extra}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
