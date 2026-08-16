#!/usr/bin/env python3
"""Pass one of error-handling: parse ruff + bandit JSON into findings rows.

Both tools are JSON-native (spec #365's R1 recon) — `uvx ruff check --select
BLE,TRY,B904,SIM105 --output-format json <scope>` gives an array of objects
(`filename`, `location.row`, `code`, `message`); `uvx bandit -r <scope> -f
json -t B110,B112` gives `.results[]` (`filename`, `line_number`, `test_id`,
`issue_text`). `parse_findings` merges both into rows; it never judges
justified vs unjustified — that's the judgment pass (SKILL.md) reading these
rows and re-bucketing them.

Run both tools against the SAME absolute scope path — `uvx bandit -r
"$(realpath "$scope")"` — so their `filename` fields match and same-line
hits from the two tools merge into one row instead of two.
"""

import json
import sys

_CATEGORY = {
    "BLE001": "bare-except",
    "SIM105": "try-except-pass",
    "B110": "try-except-pass",
    "B112": "try-except-continue",
    "B904": "raise-without-from",
}
# lower index wins when >1 category fires on the same line. "try-consider"
# has no direct _CATEGORY entry — it's the fallback for any ruff TRY0xx code,
# assigned in _category() below.
_PRIORITY = [
    "bare-except",
    "raise-without-from",
    "try-except-continue",
    "try-except-pass",
    "try-consider",
]


def _category(code):
    if code in _CATEGORY:
        return _CATEGORY[code]
    if code.startswith("TRY"):
        return "try-consider"
    return None


def parse_findings(ruff_json, bandit_json):
    """Parse ruff's and bandit's JSON output into findings rows.

    Pure: raw captured JSON text for both tools in, a list of findings-schema
    dict rows out. No subprocess, no filesystem. `bucket` defaults to "fix" —
    a caught-and-dropped exception is a real smell by construction, same
    reasoning `duplication`'s parser uses for a token clone — pass two
    downgrades a row to "justified" once it reads the except in context. Hits
    from the two tools on the same (file, line) merge into one row noting
    every code that fired.
    """
    hits = {}  # (file, line) -> list of (code, category, message)
    for item in json.loads(ruff_json):
        cat = _category(item["code"])
        if cat is None:
            continue
        key = (item["filename"], item["location"]["row"])
        hits.setdefault(key, []).append((item["code"], cat, item["message"]))
    for item in json.loads(bandit_json).get("results", []):
        cat = _category(item["test_id"])
        if cat is None:
            continue
        key = (item["filename"], item["line_number"])
        hits.setdefault(key, []).append((item["test_id"], cat, item["issue_text"]))

    rows = []
    for (file, line), fired in sorted(
        hits.items(), key=lambda kv: (kv[0][0], kv[0][1])
    ):
        codes = sorted({code for code, _, _ in fired})
        category = min({cat for _, cat, _ in fired}, key=_PRIORITY.index)
        messages = "; ".join(sorted({msg for _, _, msg in fired}))
        rows.append(
            {
                "bucket": "fix",
                "file": file,
                "line": line,
                "category": category,
                "summary": f"{category.replace('-', ' ')} at {file}:{line} ({', '.join(codes)})",
                "failure": f"exception silenced with no visible re-raise or log: {messages}",
                "extra": {"codes": codes},
            }
        )
    return rows


def _selfcheck():
    ruff_json = json.dumps(
        [
            {
                "filename": "sample.py",
                "location": {"row": 14},
                "code": "BLE001",
                "message": "Do not catch blind exception: `Exception`",
            },
            {
                "filename": "sample.py",
                "location": {"row": 23},
                "code": "SIM105",
                "message": "Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`",
            },
            {
                "filename": "sample.py",
                "location": {"row": 25},
                "code": "BLE001",
                "message": "Do not catch blind exception: `Exception`",
            },
        ]
    )
    bandit_json = json.dumps(
        {
            "results": [
                {
                    "filename": "sample.py",
                    "line_number": 14,
                    "test_id": "B110",
                    "issue_text": "Try, Except, Pass detected.",
                },
                {
                    "filename": "sample.py",
                    "line_number": 25,
                    "test_id": "B110",
                    "issue_text": "Try, Except, Pass detected.",
                },
            ]
        }
    )
    rows = parse_findings(ruff_json, bandit_json)
    assert len(rows) == 3, rows

    # line 14: ruff BLE001 + bandit B110 merge into one row
    line14 = next(r for r in rows if r["line"] == 14)
    assert line14["category"] == "bare-except", line14
    assert line14["bucket"] == "fix"
    assert line14["extra"]["codes"] == ["B110", "BLE001"]

    # line 23: ruff SIM105 only, no bandit hit at this line
    line23 = next(r for r in rows if r["line"] == 23)
    assert line23["category"] == "try-except-pass", line23
    assert line23["extra"]["codes"] == ["SIM105"]

    # line 25: ruff BLE001 + bandit B110 merge into one row
    line25 = next(r for r in rows if r["line"] == 25)
    assert line25["category"] == "bare-except", line25
    assert line25["extra"]["codes"] == ["B110", "BLE001"]

    empty = parse_findings(json.dumps([]), json.dumps({"results": []}))
    assert empty == []

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if len(argv) < 3:
        print(
            "usage: audit.py <ruff.json> <bandit.json> | --selfcheck", file=sys.stderr
        )
        sys.exit(1)
    ruff_json = open(argv[1], encoding="utf-8").read()
    bandit_json = open(argv[2], encoding="utf-8").read()
    for row in parse_findings(ruff_json, bandit_json):
        print(json.dumps(row))


if __name__ == "__main__":
    main(sys.argv)
