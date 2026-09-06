#!/usr/bin/env python3
"""Pass one of duplication: parse jscpd's JSON output into findings rows.

jscpd is JSON-native (spec #365's R1 recon) — `jscpd --reporters json
--output <dir> <scope>` writes `<dir>/jscpd-report.json` with a
`.duplicates[]` array. `parse_jscpd` extracts one findings row per duplicate
pair; it never judges consolidate vs keep — that's the judgment pass
(SKILL.md) reading these rows and re-bucketing them.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402


def parse_jscpd(json_str):
    """Parse jscpd's JSON report into findings rows.

    Pure: raw jscpd JSON text in, a list of findings-schema dict rows out. No
    subprocess, no filesystem. `bucket` defaults to "consolidate" — a token
    clone is a real clone by construction — the judgment pass can downgrade
    it to "keep" for intentional/acceptable duplication. `failure` is empty;
    naming the concrete drift is the judgment pass's job.
    """
    data = json.loads(json_str)
    rows = []
    for dup in data.get("duplicates", []):
        first = dup["firstFile"]
        second = dup["secondFile"]
        tokens = dup["tokens"]
        row = auditlib.finding(
            "consolidate",
            first["name"],
            first["start"],
            "token-clone",
            f"{first['name']}:{first['start']} duplicates {second['name']}:{second['start']} ({tokens} tokens)",
            clone_tokens=tokens,
        )
        row["owner"] = f"{second['name']}:{second['start']}"
        rows.append(row)
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
    assert row["failure"] == ""
    assert row["owner"] == "b.py:6"

    empty = parse_jscpd(json.dumps({"duplicates": []}))
    assert empty == []

    print("ok")


def main(argv):
    # supports `--selfcheck` via auditlib.run_cli
    auditlib.run_cli(argv, _selfcheck, parse_jscpd)


if __name__ == "__main__":
    main(sys.argv)
