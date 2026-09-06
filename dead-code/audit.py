#!/usr/bin/env python3
"""Pass one of dead-code: parse vulture's text output into findings rows.

vulture has no JSON output (see spec #365's R1 recon) — its text format is the
stable contract: `path/to/file.py:LINE: unused <kind> '<name>' (<NN>%
confidence)`. `parse_vulture` extracts file/line/category/confidence
mechanically; it never decides dead vs dynamically-reached — that's the
judgment pass (SKILL.md) reading these rows and re-bucketing them.

ponytail: only the `unused <kind> '<name>' (<NN>% confidence)` line shape is
parsed — vulture's other line shape (`unreachable code after 'return' (100%
confidence)`, no quoted name) isn't in the ticket's stable-format contract and
is out of scope here.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

_VULTURE_LINE_RE = re.compile(r"^(?P<file>.+):(?P<line>\d+): unused (?P<kind>[\w ]+) '(?P<name>[^']+)' \((?P<confidence>\d+)% confidence\)$")


def parse_vulture(text):
    """Parse vulture's text output into findings rows.

    Pure: raw vulture stdout in, a list of findings-schema dict rows out. No
    subprocess, no filesystem. `bucket` defaults to "unsure" and `failure` is
    empty — the dead/dynamic/unsure verdict is the LLM-triage pass's job, not
    this parser's.
    """
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


def _selfcheck():
    sample = "\n".join([
        "foo.py:12: unused function 'helper' (60% confidence)",
        "bar.py:3: unused import 'os' (90% confidence)",
    ])
    rows = parse_vulture(sample)
    assert len(rows) == 2, rows

    assert rows[0]["file"] == "foo.py"
    assert rows[0]["line"] == 12
    assert rows[0]["category"] == "unused-function"
    assert rows[0]["extra"]["confidence"] == 60
    assert rows[0]["bucket"] == "unsure"
    assert rows[0]["failure"] == ""
    assert "helper" in rows[0]["summary"]

    assert rows[1]["file"] == "bar.py"
    assert rows[1]["line"] == 3
    assert rows[1]["category"] == "unused-import"
    assert rows[1]["extra"]["confidence"] == 90
    assert "os" in rows[1]["summary"]

    print("ok")


def main(argv):
    # supports `--selfcheck` via auditlib.run_cli
    auditlib.run_cli(argv, _selfcheck, parse_vulture)


if __name__ == "__main__":
    main(sys.argv)
