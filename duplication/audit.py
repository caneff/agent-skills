#!/usr/bin/env python3
"""Pass one of duplication: parse jscpd's JSON output into findings rows.

jscpd is JSON-native (spec #365's R1 recon) — `jscpd --reporters json
--output <dir> <scope>` writes `<dir>/jscpd-report.json` with a
`.duplicates[]` array. `parse_jscpd` extracts one findings row per duplicate
pair; it never judges consolidate vs keep — that's the judgment pass
(SKILL.md) reading these rows and re-bucketing them.
"""
import json
import sys


def parse_jscpd(json_str):
    """Parse jscpd's JSON report into findings rows.

    Pure: raw jscpd JSON text in, a list of findings-schema dict rows out. No
    subprocess, no filesystem. `bucket` defaults to "consolidate" — a token
    clone is a real clone by construction — the judgment pass can downgrade
    it to "keep" for intentional/acceptable duplication.
    """
    data = json.loads(json_str)
    rows = []
    for dup in data.get("duplicates", []):
        first = dup["firstFile"]
        second = dup["secondFile"]
        tokens = dup["tokens"]
        rows.append(
            {
                "bucket": "consolidate",
                "file": first["name"],
                "line": first["start"],
                "category": "token-clone",
                "summary": f"{first['name']}:{first['start']} duplicates {second['name']}:{second['start']} ({tokens} tokens)",
                "failure": f"two copies drift; a fix to one at {first['name']}:{first['start']} silently skips the other at {second['name']}:{second['start']}",
                "extra": {"clone_tokens": tokens},
                "owner": f"{second['name']}:{second['start']}",
            }
        )
    return rows


def _selfcheck():
    sample = json.dumps(
        {
            "duplicates": [
                {
                    "firstFile": {"name": "a.py", "start": 4, "end": 19},
                    "secondFile": {"name": "b.py", "start": 6, "end": 21},
                    "format": "python",
                    "fragment": "...",
                    "lines": 16,
                    "tokens": 92,
                }
            ]
        }
    )
    rows = parse_jscpd(sample)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["file"] == "a.py"
    assert row["line"] == 4
    assert row["category"] == "token-clone"
    assert row["bucket"] == "consolidate"
    assert row["extra"]["clone_tokens"] == 92
    assert "b.py:6" in row["summary"]
    assert "a.py:4" in row["failure"] and "b.py:6" in row["failure"]
    assert row["owner"] == "b.py:6"

    empty = parse_jscpd(json.dumps({"duplicates": []}))
    assert empty == []

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    text = sys.stdin.read() if len(argv) < 2 else open(argv[1], encoding="utf-8").read()
    for row in parse_jscpd(text):
        print(json.dumps(row))


if __name__ == "__main__":
    main(sys.argv)
