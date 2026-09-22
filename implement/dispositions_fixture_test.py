#!/usr/bin/env python3
"""The dispositions sidecar fixture and the grammar SKILL.md § Review states
must agree (#1025, #1027). Every readers' test binds to the fixture, so a
form the prose adds that the fixture lacks is a form no reader is tested on,
and a fixture line the prose never states is a form no writer produces.

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


def test_the_prose_states_every_outcome():
    outcomes = {f[0] for f in stated_forms()}
    assert outcomes == {"fixed", "disputed", "filed", "handed-back", "leftover"}, outcomes


def test_every_stated_form_has_a_fixture_line():
    missing = stated_forms() - fixture_forms()
    assert not missing, f"forms § Review states with no fixture line: {missing}"


def test_every_fixture_line_is_a_stated_form():
    extra = fixture_forms() - stated_forms()
    assert not extra, f"fixture lines § Review never states: {extra}"


def test_the_leftover_line_carries_every_field_non_empty():
    with open(FIXTURE) as fh:
        objs = [json.loads(raw) for raw in fh if raw.strip()]
    leftovers = [o for o in objs if o["outcome"] == "leftover"]
    assert len(leftovers) == 1, leftovers
    for field in ("id", "file", "title", "severity", "text"):
        value = leftovers[0].get(field)
        assert isinstance(value, str) and value and "\n" not in value, (field, value)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
