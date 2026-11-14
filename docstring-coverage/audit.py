#!/usr/bin/env python3
"""Pass one of docstring-coverage: parse ruff D + interrogate text into findings rows.

ruff D1xx is JSON-native (spec #365's R1 recon); interrogate has no JSON
output — its text summary is the stable contract, exactly like vulture's text
was for dead-code. `parse_coverage` pulls one finding row per ruff D1xx hit
(private and already-documented symbols are naturally absent from that
output — ruff's own rule semantics do the filtering, no hand-filter here) and
scrapes interrogate's overall coverage percentage onto every row's
`extra.coverage`. It never judges document vs skip — that's the judgment pass
(SKILL.md) reading these rows and re-bucketing them.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

_CATEGORY = {
    "D100": "missing-module-docstring",
    "D101": "missing-class-docstring",
    "D102": "missing-method-docstring",
    "D103": "missing-function-docstring",
    "D104": "missing-package-docstring",
    "D105": "missing-magic-method-docstring",
    "D106": "missing-class-docstring",
    "D107": "missing-init-docstring",
}

_COVERAGE_RE = re.compile(r"actual:\s*([\d.]+)%")


def parse_coverage(ruff_json, interrogate_text):
    """Parse ruff's D1xx JSON and interrogate's text summary into findings rows.

    Pure: raw captured ruff JSON text and interrogate stdout text in, a list
    of findings-schema dict rows out. No subprocess, no filesystem. `bucket`
    defaults to "document" — a ruff D1xx hit is a real missing-docstring
    candidate by construction, same reasoning error-handling's parser uses
    for a caught-and-dropped exception. `failure` is empty — the
    document-vs-skip verdict is the judgment pass's job. Every row carries
    the same `extra.coverage`, scraped once from interrogate's summary line.
    """
    m = _COVERAGE_RE.search(interrogate_text)
    coverage = float(m.group(1)) if m else None

    rows = []
    for item in json.loads(ruff_json):
        category = _CATEGORY.get(item["code"])
        if category is None:
            continue
        rows.append(
            auditlib.finding(
                "document",
                item["filename"],
                item["location"]["row"],
                category,
                f"{category.replace('-', ' ')} at {item['filename']}:{item['location']['row']}",
                coverage=coverage,
            )
        )
    return rows


def main(argv):
    auditlib.run_cli(
        argv, parse_coverage, nargs=2,
        usage="usage: audit.py <ruff.json> <interrogate.txt>",
    )


if __name__ == "__main__":
    main(sys.argv)
