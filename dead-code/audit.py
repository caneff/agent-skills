#!/usr/bin/env python3
"""Pass one of dead-code: parse vulture's text output into findings rows.

vulture has no JSON output — its text format is the
stable contract: `path/to/file.py:LINE: unused <kind> '<name>' (<NN>%
confidence)`. `parse_vulture` extracts file/line/category/confidence
mechanically; it never decides dead vs dynamically-reached — that's the
judgment pass (SKILL.md) reading these rows and re-bucketing them.

ponytail: only the `unused <kind> '<name>' (<NN>% confidence)` line shape is
parsed — vulture's other line shape (`unreachable code after 'return' (100%
confidence)`, no quoted name) isn't in the stable-format contract and
is out of scope here.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

_VULTURE_LINE_RE = re.compile(r"^(?P<file>.+):(?P<line>\d+): unused (?P<kind>[\w ]+) '(?P<name>[^']+)' \((?P<confidence>\d+)% confidence\)$")


def parse_vulture(text):
    """Pure: raw vulture stdout in, findings-schema dict rows out. No
    subprocess, no filesystem."""
    rows = []
    for line in text.splitlines():
        m = _VULTURE_LINE_RE.match(line.strip())
        if not m:
            continue
        kind = m.group("kind").strip()
        name = m.group("name")
        confidence = int(m.group("confidence"))
        rows.append(
            auditlib.finding(
                "unsure",
                m.group("file"),
                int(m.group("line")),
                f"unused-{kind.replace(' ', '-')}",
                f"unused {kind} '{name}'",
                confidence=confidence,
            )
        )
    return rows


def main(argv):
    auditlib.run_cli(argv, parse_vulture)


if __name__ == "__main__":
    main(sys.argv)
