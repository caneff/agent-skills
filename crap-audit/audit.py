#!/usr/bin/env python3
"""Pass one of crap-audit: score every function's CRAP (Change Risk Anti-
Patterns), CC² × (1 − coverage)³ + CC, from already-captured radon and
coverage.py JSON. No subprocess in `normalize` or `score` — both take
already-captured JSON, which is what makes them fixture-testable offline.

`normalize` joins radon's per-function complexity to coverage.py's
per-function coverage on (file, start line) — coverage.py's
`functions[*].start_line` matches radon's `lineno` exactly (verified in
`docs/research/crap-python-tooling.md`, `research/crap-python-tooling`
branch, commit `a95d390`), so no name-matching is needed even
though the two tools spell nested-function names differently (radon: a bare
name inside `closures`; coverage.py: a dotted qualname). A function entirely
absent from coverage.json (its file was never imported by the test run)
counts as 0% covered on both axes, per the ticket's missing-data rule.

`score` applies the formula, buckets findings against the floor, and
suggests the two gate values. The judgment pass (bucket beyond score-band,
real prose) is a later skill, not this file.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "all-audits", "harness"))
import auditlib  # noqa: E402

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
    matched_files = 0
    for file, entries in radon_json.items():
        # coverage.py's `""` entry is the whole-module summary, always
        # `start_line: 1`, emitted last — join on it and every function
        # defined on line 1 silently inherits the module's coverage instead
        # of its own.
        by_line = {
            func["start_line"]: func["summary"]
            for cov_name, func in files.get(file, {}).get("functions", {}).items()
            if cov_name
        }
        if file in files:
            matched_files += 1
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
    if radon_json and files and matched_files == 0:
        raise ValueError(
            "radon and coverage.json share no file keys — "
            f"radon: {sorted(radon_json)[:3]}..., coverage: {sorted(files)[:3]}...; "
            "likely an absolute-vs-relative path mismatch between the two tool "
            "invocations. Every function would silently read as 0% covered; "
            "refusing to score on that."
        )
    # A *partial* mismatch: some radon files didn't match, but not all did.
    # Two legal reasons a radon file has no coverage.json entry: it was never
    # imported by the test run (real 0%, e.g. this repo's own untested.py
    # fixture) or it's outside coverage's `source` scope on purpose. Neither
    # of those leftover coverage-only files shares a basename with the
    # unmatched radon file — a real distinct file has no reason to. If a
    # basename does collide, it's the same file spelled two ways (one
    # radon's, one coverage's), not a genuinely untested one, and every
    # function in it would silently read as 0% covered.
    unmatched_radon = set(radon_json) - set(files)
    unmatched_coverage_basenames = {os.path.basename(f) for f in set(files) - set(radon_json)}
    collided = {f for f in unmatched_radon if os.path.basename(f) in unmatched_coverage_basenames}
    if collided:
        raise ValueError(
            f"radon file(s) {sorted(collided)} share a basename with an "
            "unmatched coverage.json file but not the exact key — likely "
            "the same file under two path spellings between the two tool "
            "invocations. Refusing to silently score it 0% covered."
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
        # `axis` names which of stmt/branch was actually measured; the other
        # is filled with 100.0 only so it can't win min() in score() — it is
        # not a real number and score() must not report it as one.
        if cov is None:
            stmt_cov = branch_cov = 0.0
            axis = "both"
        elif kind == "stmt":
            stmt_cov, branch_cov = float(cov), 100.0
            axis = "stmt"
        elif kind == "branch":
            stmt_cov, branch_cov = 100.0, float(cov)
            axis = "branch"
        else:  # "N/A" with cov not None -> structural_na
            stmt_cov = branch_cov = 100.0
            axis = "both"
        rows.append(
            {
                "file": method["src"],
                "name": method["method"],
                "line": method["lineStart"],
                "complexity": method["cc"],
                "statement_coverage": stmt_cov,
                "branch_coverage": branch_cov,
                "coverage_axis": axis,
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


def _recommend(complexity):
    """Per-finding remediation leverage: 'write tests' when full coverage
    would drop CRAP under the classic gate (testing alone gets there), else
    'refactor' (complexity itself already meets/exceeds the gate, so no
    coverage improvement escapes it — the fix has to shrink complexity).

    CRAP at coverage=1.0 collapses to bare complexity — the (1-cov)^3
    penalty term vanishes — so the projection is just `complexity` itself."""
    projected = complexity
    action = "write tests" if projected < CLASSIC_GATE else "refactor"
    return {"action": action, "projected_crap": projected}


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
        # `coverage_axis` (TS rows only) names which axis was actually
        # measured — the other was filled with a synthetic 100.0 so it
        # can't win score()'s min(); that synthetic number must never be
        # reported as a real percentage anywhere the row is emitted, ranking
        # included, so it's nulled here rather than only at the findings step.
        axis = row.get("coverage_axis", "both")
        ranking.append(
            {
                **row,
                "statement_coverage": row["statement_coverage"] if axis in ("both", "stmt") else None,
                "branch_coverage": row["branch_coverage"] if axis in ("both", "branch") else None,
                "coverage": coverage,
                "crap": crap,
            }
        )
    ranking.sort(key=lambda r: r["crap"], reverse=True)

    findings = []
    under_floor = []
    for r in ranking:
        if r["crap"] >= floor:
            findings.append(
                auditlib.finding(
                    _bucket(r["crap"]),
                    r["file"],
                    r["line"],
                    _category(r["complexity"], r["coverage"]),
                    f"{r['name']} scores CRAP {r['crap']:.1f} "
                    f"(complexity {r['complexity']}, coverage {r['coverage'] * 100:.0f}%)",
                    f"a change to {r['name']} is both likely to break "
                    "something and unlikely to be caught by a test",
                    complexity=r["complexity"],
                    statement_coverage=r["statement_coverage"],
                    branch_coverage=r["branch_coverage"],
                    coverage=r["coverage"],
                    crap=r["crap"],
                    recommendation=_recommend(r["complexity"]),
                )
            )
        else:
            under_floor.append(r)

    max_crap = ranking[0]["crap"] if ranking else 0
    gates = {"classic": CLASSIC_GATE, "above_current_max": int(max_crap) + 1}

    return {
        "findings": findings,
        "under_floor": {"count": len(under_floor), "sample": under_floor[:UNDER_FLOOR_SAMPLE]},
        "gates": gates,
        "ranking": ranking,
    }


def _parse_default(radon_text, coverage_text):
    """The two-file default path's `parse`, as `run_cli` expects: one row
    out — the whole `score()` result — so `run_cli`'s `for row in parse(...):
    print(json.dumps(row))` reproduces the prior single-line output exactly.
    """
    return [score(normalize(json.loads(radon_text), json.loads(coverage_text)))]


def _selfcheck():
    """Reproduce fixtures/sample_project's known findings — the same fixture
    `audit_test.py`'s test_cli_main_prints_whole_score_result pins against."""
    fixtures = os.path.join(os.path.dirname(__file__), "fixtures", "sample_project")
    radon_json = json.load(open(os.path.join(fixtures, "radon.json"), encoding="utf-8"))
    coverage_json = json.load(open(os.path.join(fixtures, "coverage.json"), encoding="utf-8"))
    result = score(normalize(radon_json, coverage_json))
    assert len(result["findings"]) == 2, result
    assert {row["file"] for row in result["findings"]} == {"sample.py"}, result
    assert {row["line"] for row in result["findings"]} == {2, 17}, result
    for row in result["findings"]:
        assert set(row) == {"bucket", "file", "line", "category", "summary", "failure", "extra"}, row
    print("ok")


def main(argv):
    if argv[1:2] == ["--ts"]:
        if len(argv) < 3:
            print("usage: audit.py --ts <crap_typescript.json>", file=sys.stderr)
            sys.exit(1)
        report_json = json.load(open(argv[2], encoding="utf-8"))
        print(json.dumps(score(normalize_ts(report_json))))
        return
    auditlib.run_cli(
        argv,
        _selfcheck,
        _parse_default,
        nargs=2,
        usage="usage: audit.py <radon.json> <coverage.json> | --ts <ts.json> | --selfcheck",
    )


if __name__ == "__main__":
    main(sys.argv)
