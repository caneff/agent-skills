#!/usr/bin/env python3
"""Tests for crap-audit's scoring core: normalize, score, and the thin CLI main.

Assert-based, no framework — matches the audit family's convention (see
dead-code/audit.py's `_selfcheck`). One function per acceptance criterion of
ticket #505; run directly with `python3 crap-audit/test_audit.py`.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import audit  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "sample_project")
TS_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "ts_sample_project")


def _load_fixture():
    radon_json = json.load(open(os.path.join(FIXTURES, "radon.json"), encoding="utf-8"))
    coverage_json = json.load(open(os.path.join(FIXTURES, "coverage.json"), encoding="utf-8"))
    return radon_json, coverage_json


def test_reproduces_answer_key_exactly():
    """AC1: running the script over the fixture JSON reproduces the answer key."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    by_name = {r["name"]: r for r in result["ranking"]}
    assert round(by_name["inner"]["crap"], 3) == 32.244, by_name["inner"]
    assert by_name["uncovered_fn"]["crap"] == 20.0, by_name["uncovered_fn"]
    assert by_name["entirely_uncovered"]["crap"] == 12.0, by_name["entirely_uncovered"]
    assert by_name["outer"]["crap"] == 1.0, by_name["outer"]
    assert by_name["branchless_fn"]["crap"] == 1.0, by_name["branchless_fn"]

    ranked_names = [r["name"] for r in result["ranking"]]
    assert ranked_names == [
        "inner",
        "uncovered_fn",
        "entirely_uncovered",
        "outer",
        "branchless_fn",
    ], ranked_names


def test_nested_uncovered_and_branchless_score_per_spec():
    """AC2: nested (radon closures), missing-data, and branchless functions
    each score per the spec's rules, not just happen to land somewhere."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    by_name = {r["name"]: r for r in rows}

    # nested: radon only reports `inner` inside `outer`'s "closures" list —
    # normalize must recurse to find it at all.
    assert by_name["inner"]["complexity"] == 6
    assert by_name["inner"]["line"] == 2

    # missing coverage data entirely (untested.py never imported) -> 0% both axes.
    assert by_name["entirely_uncovered"]["statement_coverage"] == 0.0
    assert by_name["entirely_uncovered"]["branch_coverage"] == 0.0

    # branchless: coverage.py reports 100% branch coverage when there are no
    # branches, so effective coverage reduces to statement coverage alone.
    eff = audit._effective_coverage(by_name["branchless_fn"])
    assert eff == 1.0


def test_findings_validate_against_findings_schema():
    """AC3: findings rows carry every required findings-schema field."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    assert len(result["findings"]) == 2
    for finding in result["findings"]:
        for field in ("bucket", "file", "line", "category", "summary", "failure"):
            assert field in finding and finding[field], finding
        assert finding["bucket"] in ("critical", "hotspot")
        assert isinstance(finding["line"], int)
        assert "extra" in finding and isinstance(finding["extra"], dict)


def test_under_floor_is_count_and_sample_not_full_rows():
    """AC4: under-floor output is a count + a sampling, not every clean row;
    the full ranking is emitted separately and does carry every row."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    assert result["under_floor"]["count"] == 3
    assert len(result["under_floor"]["sample"]) <= result["under_floor"]["count"]
    assert len(result["under_floor"]["sample"]) > 0

    assert len(result["ranking"]) == 5
    assert len(result["findings"]) + result["under_floor"]["count"] == len(result["ranking"])


def test_gate_suggestions_present_and_correct():
    """AC5: both suggested gate values are present and correct for the fixture."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    assert result["gates"]["classic"] == 30
    assert result["gates"]["above_current_max"] == 33


def test_cli_main_prints_findings_jsonl():
    """The thin CLI main reads the two JSON files and prints findings.jsonl lines."""
    out = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "audit.py"),
            os.path.join(FIXTURES, "radon.json"),
            os.path.join(FIXTURES, "coverage.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert {row["file"] for row in lines} == {"sample.py"}
    assert {row["line"] for row in lines} == {2, 17}


def _load_ts_fixture():
    return json.load(open(os.path.join(TS_FIXTURES, "crap_typescript.json"), encoding="utf-8"))


def test_normalize_ts_reproduces_captured_tool_crap_via_unchanged_score():
    """TS AC: normalize_ts -> ticket 1's score() (imported, not reimplemented)
    reproduces @barney-media/crap-typescript-core's own `crap` field for every
    measured row -- the two coverage definitions agree, per the ticket's
    verify-first requirement."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    result = audit.score(rows)
    by_name = {r["name"]: r for r in result["ranking"]}

    captured_crap = {m["method"]: m["crap"] for m in report["methods"]}
    for name, row in by_name.items():
        assert round(row["crap"], 6) == round(captured_crap[name], 6), (name, row, captured_crap[name])

    assert round(by_name["inner"]["crap"], 3) == 24.432
    assert by_name["uncoveredFn"]["crap"] == 20.0
    assert by_name["entirelyUncovered"]["crap"] == 6.0
    assert by_name["arrowFn"]["crap"] == 2.0
    assert by_name["outer"]["crap"] == 1.0
    assert by_name["branchlessFn"]["crap"] == 1.0


def test_normalize_ts_attributes_the_arrow_function():
    """TS AC: the fixture's arrow function is attributed a row at all, with
    the right file/line/complexity -- normalize_ts must not silently drop
    arrow-function methods the way a naive declaration-only walk would."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    by_name = {r["name"]: r for r in rows}

    assert "arrowFn" in by_name
    row = by_name["arrowFn"]
    assert row["file"] == "src/sample.ts"
    assert row["line"] == 36
    assert row["complexity"] == 2
    assert row["statement_coverage"] == 100.0
    assert row["branch_coverage"] == 100.0


def test_normalize_ts_missing_coverage_report_counts_as_zero_both_axes():
    """Missing-data rule, same as ticket 1's Python path: a method the tool
    could not attribute any coverage to at all (cov=null, covKind="N/A",
    e.g. missing_report/unparseable_report/fnmap_conflict) counts as 0%
    covered on both axes, not skipped and not silently 100%."""
    report = {
        "status": "failed",
        "threshold": 6,
        "methods": [
            {
                "status": "skipped",
                "crap": None,
                "cc": 3,
                "cov": None,
                "covKind": "N/A",
                "method": "orphaned",
                "src": "src/orphan.ts",
                "lineStart": 5,
                "lineEnd": 9,
            }
        ],
    }
    rows = audit.normalize_ts(report)
    assert rows == [
        {
            "file": "src/orphan.ts",
            "name": "orphaned",
            "line": 5,
            "complexity": 3,
            "statement_coverage": 0.0,
            "branch_coverage": 0.0,
        }
    ]


def test_normalize_ts_structural_na_counts_as_fully_covered_both_axes():
    """A method with nothing to instrument at all (structural_na, e.g. an
    ambient/abstract signature) also reports cov=100/covKind="N/A" --
    distinct from the missing-report case above only by cov not being null.
    Trivially satisfied, same treatment as a branchless Python function."""
    report = {
        "status": "passed",
        "threshold": 6,
        "methods": [
            {
                "status": "passed",
                "crap": 1,
                "cc": 1,
                "cov": 100,
                "covKind": "N/A",
                "method": "signatureOnly",
                "src": "src/orphan.ts",
                "lineStart": 12,
                "lineEnd": 12,
            }
        ],
    }
    rows = audit.normalize_ts(report)
    assert rows[0]["statement_coverage"] == 100.0
    assert rows[0]["branch_coverage"] == 100.0


def test_ts_findings_validate_against_findings_schema():
    """TS AC: score() -- ticket 1's, unmodified -- applied to normalize_ts's
    rows produces findings-schema-valid rows, same as the Python path."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    result = audit.score(rows)

    assert len(result["findings"]) == 2
    for finding in result["findings"]:
        for field in ("bucket", "file", "line", "category", "summary", "failure"):
            assert field in finding and finding[field], finding
        assert finding["bucket"] in ("critical", "hotspot")


def test_cli_main_ts_mode_prints_findings_jsonl():
    """The thin CLI's `--ts <report.json>` mode reads the captured tool
    report and prints findings.jsonl lines via the same score()."""
    out = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "audit.py"),
            "--ts",
            os.path.join(TS_FIXTURES, "crap_typescript.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert {row["file"] for row in lines} == {"src/sample.ts"}


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
