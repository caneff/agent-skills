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


def main(argv):
    auditlib.run_cli(argv, parse_jscpd)


if __name__ == "__main__":
    main(sys.argv)
