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


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
