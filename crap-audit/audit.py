#!/usr/bin/env python3
"""Pass one of crap-audit: score every function's CRAP (Change Risk Anti-
Patterns), CC² × (1 − coverage)³ + CC, from already-captured radon and
coverage.py JSON. No subprocess in `normalize` or `score` — both take
already-captured JSON, which is what makes them fixture-testable offline.

`normalize` joins radon's per-function complexity to coverage.py's
per-function coverage on (file, start line) — coverage.py's
`functions[*].start_line` matches radon's `lineno` exactly (verified via
`docs/research/crap-python-tooling.md`), so no name-matching is needed even
though the two tools spell nested-function names differently (radon: a bare
name inside `closures`; coverage.py: a dotted qualname). A function entirely
absent from coverage.json (its file was never imported by the test run)
counts as 0% covered on both axes, per the ticket's missing-data rule.

`score` applies the formula, buckets findings against the floor, and
suggests the two gate values. The judgment pass (bucket beyond score-band,
real prose) is a later skill, not this file.
"""
import json
import math
import sys

FLOOR = 15
CLASSIC_GATE = 30
UNDER_FLOOR_SAMPLE = 5


def _flatten_radon(entries):
    """Recurse radon `cc -j` entries into (name, lineno, complexity) rows.

    Skips `class` entries themselves (their complexity is a rollup, not a
    function) but descends into a class's `methods`. Recurses into
    `closures` too, or a nested (non-method) function is silently dropped —
    radon only lists it there, never as a flattened top-level entry.
    """
    rows = []
    for entry in entries:
        if entry["type"] in ("function", "method"):
            rows.append((entry["name"], entry["lineno"], entry["complexity"]))
            rows.extend(_flatten_radon(entry.get("closures", [])))
        elif entry["type"] == "class":
            rows.extend(_flatten_radon(entry.get("methods", [])))
    return rows


def normalize(radon_json, coverage_json):
    """Captured radon + coverage.py JSON -> language-neutral function rows.

    One row per function: file, name, line, complexity, statement_coverage,
    branch_coverage (both 0-100 floats; branch_coverage is coverage.py's own
    reported value, which is 100.0 for a function with zero branches — the
    branch term is trivially satisfied, so callers get statement-only
    coverage for free via min() without a special case here).
    """
    rows = []
    files = coverage_json.get("files", {})
    for file, entries in radon_json.items():
        by_line = {
            func["start_line"]: func["summary"]
            for func in files.get(file, {}).get("functions", {}).values()
        }
        for name, lineno, complexity in _flatten_radon(entries):
            summary = by_line.get(lineno)
            stmt_cov = summary["percent_covered"] if summary else 0.0
            branch_cov = summary["percent_branches_covered"] if summary else 0.0
            rows.append(
                {
                    "file": file,
                    "name": name,
                    "line": lineno,
                    "complexity": complexity,
                    "statement_coverage": stmt_cov,
                    "branch_coverage": branch_cov,
                }
            )
    return rows


def normalize_ts(report_json):
    """Captured `@barney-media/crap-typescript-core` `--format json` report ->
    the same language-neutral function rows `normalize` produces.

    The report only exposes the already-combined `cov`/`covKind` per method
    (`covKind` names which axis -- stmt or branch -- was the lower/measured
    one), never both raw percentages, because the package's own
    `combineCoverageMetrics` does exactly `min(measured percents)` (verified
    by reading `coverageNormalization.js` in the published package), the same
    rule `score()`'s `_effective_coverage` applies. So a row's non-dominant
    axis is filled with 100.0 (does not affect the min) rather than
    reconstructed -- reusing `score()` unchanged still reproduces the tool's
    own `crap` value exactly.

    `cov is None` (`covKind == "N/A"` for a missing/unparseable/ambiguous
    coverage report) is the same missing-data rule as `normalize`'s Python
    path: 0% both axes. `cov == 100` with `covKind == "N/A"` is the other
    "N/A" case -- structural_na, nothing to instrument at all (e.g. an
    ambient signature) -- trivially satisfied, 100% both axes, same
    treatment as a branchless Python function reporting 100% branch
    coverage.
    """
    rows = []
    for method in report_json["methods"]:
        cov = method["cov"]
        kind = method["covKind"]
        if cov is None:
            stmt_cov = branch_cov = 0.0
        elif kind == "stmt":
            stmt_cov, branch_cov = float(cov), 100.0
        elif kind == "branch":
            stmt_cov, branch_cov = 100.0, float(cov)
        else:  # "N/A" with cov not None -> structural_na
            stmt_cov = branch_cov = 100.0
        rows.append(
            {
                "file": method["src"],
                "name": method["method"],
                "line": method["lineStart"],
                "complexity": method["cc"],
                "statement_coverage": stmt_cov,
                "branch_coverage": branch_cov,
            }
        )
    return rows


def _effective_coverage(row):
    """min(statement, branch) as a 0-1 fraction — the ticket's coverage rule."""
    return min(row["statement_coverage"], row["branch_coverage"]) / 100.0


def _crap(complexity, coverage):
    return complexity**2 * (1 - coverage) ** 3 + complexity


def _category(complexity, coverage):
    """Dominant ingredient: whether the coverage penalty or the flat
    complexity term drives more of the score."""
    penalty = complexity**2 * (1 - coverage) ** 3
    return "low-coverage" if penalty >= complexity else "high-complexity"


def _bucket(crap):
    return "critical" if crap >= CLASSIC_GATE else "hotspot"


def score(rows, floor=FLOOR):
    """Score every row; split into findings (>= floor) vs under-floor;
    suggest two adoptable gate values off the full ranking.

    Returns {findings, under_floor: {count, sample}, gates, ranking}.
    `ranking` always carries every row (the calibration asset); `findings`
    and `under_floor.sample` are the two views a reader actually reads.
    """
    ranking = []
    for row in rows:
        coverage = _effective_coverage(row)
        crap = _crap(row["complexity"], coverage)
        ranking.append({**row, "coverage": coverage, "crap": crap})
    ranking.sort(key=lambda r: r["crap"], reverse=True)

    findings = []
    under_floor = []
    for r in ranking:
        if r["crap"] >= floor:
            findings.append(
                {
                    "bucket": _bucket(r["crap"]),
                    "file": r["file"],
                    "line": r["line"],
                    "category": _category(r["complexity"], r["coverage"]),
                    "summary": f"{r['name']} scores CRAP {r['crap']:.1f} "
                    f"(complexity {r['complexity']}, coverage {r['coverage'] * 100:.0f}%)",
                    "failure": f"a change to {r['name']} is both likely to break "
                    "something and unlikely to be caught by a test",
                    "extra": {
                        "complexity": r["complexity"],
                        "statement_coverage": r["statement_coverage"],
                        "branch_coverage": r["branch_coverage"],
                        "coverage": r["coverage"],
                        "crap": r["crap"],
                    },
                }
            )
        else:
            under_floor.append(r)

    max_crap = ranking[0]["crap"] if ranking else 0
    gates = {"classic": CLASSIC_GATE, "above_current_max": math.floor(max_crap) + 1}

    return {
        "findings": findings,
        "under_floor": {"count": len(under_floor), "sample": under_floor[:UNDER_FLOOR_SAMPLE]},
        "gates": gates,
        "ranking": ranking,
    }


def _selfcheck():
    radon_json = {"a.py": [{"type": "function", "name": "f", "lineno": 1, "complexity": 4, "closures": []}]}
    coverage_json = {"files": {"a.py": {"functions": {"f": {"start_line": 1, "summary": {"percent_covered": 50.0, "percent_branches_covered": 50.0}}}}}}
    rows = normalize(radon_json, coverage_json)
    assert rows == [
        {"file": "a.py", "name": "f", "line": 1, "complexity": 4, "statement_coverage": 50.0, "branch_coverage": 50.0}
    ], rows
    result = score(rows, floor=1)
    assert round(result["findings"][0]["extra"]["crap"], 3) == 6.0, result
    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if argv[1:2] == ["--ts"]:
        report_json = json.load(open(argv[2], encoding="utf-8"))
        rows = normalize_ts(report_json)
    else:
        radon_json = json.load(open(argv[1], encoding="utf-8"))
        coverage_json = json.load(open(argv[2], encoding="utf-8"))
        rows = normalize(radon_json, coverage_json)
    for finding in score(rows)["findings"]:
        print(json.dumps(finding))


if __name__ == "__main__":
    main(sys.argv)
