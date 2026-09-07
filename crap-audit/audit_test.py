#!/usr/bin/env python3
"""Tests for crap-audit's scoring core: normalize, score, and the thin CLI main.

Assert-based, no framework — matches the audit family's convention (see
dead-code/audit.py's `_selfcheck`). One function per acceptance criterion of
ticket #505; run directly with `python3 crap-audit/audit_test.py`.
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


def _parse_answer_key(path):
    """Pull {name: (crap, bucket)} out of the answer key's markdown table so
    the test binds to the doc itself, not a hand-retyped copy of its
    numbers that can silently drift from it."""
    import re

    rows = {}
    for line in open(path, encoding="utf-8"):
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        name = re.match(r"`([^`]+)`", cells[0]).group(1)
        crap = float(re.search(r"\*\*([\d.]+)\*\*", cells[-2]).group(1))
        bucket_match = re.match(r"`([^`]+)`", cells[-1])
        bucket = bucket_match.group(1) if bucket_match else "under-floor"
        rows[name] = (crap, bucket)
    return rows


def test_matches_answer_key_md_table():
    """AC1: running the script over the fixture JSON reproduces the answer
    key, parsed live from fixtures/sample_project/answer-key.md (not
    retyped) so the doc and the code can't silently drift apart. The table's
    row order is also the doc's ranking order, so this doubles as the
    ranking-order assertion."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)
    by_name = {r["name"]: r for r in result["ranking"]}
    findings_by_line = {f["line"]: f for f in result["findings"]}

    key = _parse_answer_key(os.path.join(FIXTURES, "answer-key.md"))
    assert key, "answer-key.md table did not parse to any rows"

    ranked_names = [r["name"] for r in result["ranking"]]
    assert ranked_names == list(key), ranked_names

    for name, (crap, bucket) in key.items():
        assert round(by_name[name]["crap"], 3) == crap, name
        if bucket == "under-floor":
            assert by_name[name]["crap"] < audit.FLOOR, name
        else:
            finding = findings_by_line[by_name[name]["line"]]
            assert finding["bucket"] == bucket, name


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


def test_line1_function_does_not_inherit_module_summary():
    """P0 regression: coverage.py's `""` module-scope entry is always
    start_line 1 and is emitted last in `functions`. A real function that
    also starts on line 1 must join on its own summary, not the module's --
    else a 0%-covered function silently reads as 100% covered and its
    CRAP score vanishes from the findings.

    The synthetic JSON below only varies the coverage percentages; its
    *shape* is not assumed, it is first checked against the committed real
    coverage.py 7.16.0 capture, which already exhibits the collision
    (`outer` and `""` both at start_line 1, `""` emitted last). That
    fixture cannot catch the bug on its own because both summaries there
    happen to be 100/100 -- hence the synthetic pair."""
    _, real_coverage = _load_fixture()
    real_functions = real_coverage["files"]["sample.py"]["functions"]
    assert real_functions[""]["start_line"] == 1, "module-scope entry is not at line 1"
    assert list(real_functions)[-1] == "", "module-scope entry is not emitted last"
    assert real_functions["outer"]["start_line"] == 1, "fixture lost its line-1 collision"

    radon_json = {
        "m.py": [
            {"type": "function", "name": "first", "lineno": 1, "complexity": 4, "closures": []}
        ]
    }
    coverage_json = {
        "files": {
            "m.py": {
                "functions": {
                    "first": {
                        "start_line": 1,
                        "summary": {"percent_covered": 0.0, "percent_branches_covered": 0.0},
                    },
                    # module-scope summary: same start_line, listed after
                    # `first` -- exactly how coverage.py 7.16.0 emits it.
                    "": {
                        "start_line": 1,
                        "summary": {"percent_covered": 100.0, "percent_branches_covered": 100.0},
                    },
                }
            }
        }
    }
    rows = audit.normalize(radon_json, coverage_json)
    assert rows[0]["statement_coverage"] == 0.0
    assert rows[0]["branch_coverage"] == 0.0

    result = audit.score(rows, floor=1)
    assert result["findings"][0]["extra"]["crap"] == 20.0


def test_normalize_raises_on_zero_matched_files_when_both_sides_nonempty():
    """P1 fix: a radon-vs-coverage.json file-key mismatch (e.g. absolute vs.
    repo-relative paths) must fail loudly, not silently score every function
    0%/0% and emit a page of fabricated `critical` findings."""
    radon_json = {"/abs/path/m.py": [{"type": "function", "name": "f", "lineno": 1, "complexity": 2, "closures": []}]}
    coverage_json = {"files": {"m.py": {"functions": {"f": {"start_line": 1, "summary": {"percent_covered": 50.0, "percent_branches_covered": 50.0}}}}}}
    try:
        audit.normalize(radon_json, coverage_json)
        assert False, "expected ValueError on zero matched file keys"
    except ValueError:
        pass


def test_normalize_raises_on_partial_basename_collision_between_unmatched_files():
    """P2 fix: a *partial* key mismatch -- some radon files join fine, one
    doesn't, and the failure is the same file spelled two ways (its
    basename collides with a leftover, otherwise-unmatched coverage file)
    -- must fail loudly too, not just score that one file 0%/0% silently.
    A genuinely-never-imported file must NOT raise -- see
    test_nested_uncovered_and_branchless_score_per_spec's untested.py,
    whose basename collides with nothing on the coverage side."""
    radon_json = {
        "a.py": [{"type": "function", "name": "f", "lineno": 1, "complexity": 1, "closures": []}],
        "/abs/path/b.py": [{"type": "function", "name": "g", "lineno": 1, "complexity": 1, "closures": []}],
    }
    coverage_json = {
        "files": {
            "a.py": {"functions": {"f": {"start_line": 1, "summary": {"percent_covered": 100.0, "percent_branches_covered": 100.0}}}},
            "b.py": {"functions": {"g": {"start_line": 1, "summary": {"percent_covered": 100.0, "percent_branches_covered": 100.0}}}},
        }
    }
    try:
        audit.normalize(radon_json, coverage_json)
        assert False, "expected ValueError on partial basename collision"
    except ValueError:
        pass


def test_normalize_does_not_raise_when_unmatched_file_shares_no_basename():
    """The legal case the partial-mismatch guard must leave alone: a radon
    file genuinely has no coverage data (never imported) and its basename
    doesn't collide with any leftover coverage file -- 0%/0% is correct,
    not an error."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)  # must not raise
    assert any(r["file"] == "untested.py" for r in rows)


def _assert_findings_schema(findings):
    """The six required findings-schema fields, non-empty, on every row —
    the one home both the Python-path and TS-path tests assert against."""
    for finding in findings:
        for field in ("bucket", "file", "line", "category", "summary", "failure"):
            assert field in finding and finding[field], finding
        assert finding["bucket"] in ("critical", "hotspot")


def test_findings_validate_against_findings_schema():
    """AC3: findings rows carry every required findings-schema field."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    assert len(result["findings"]) == 2
    _assert_findings_schema(result["findings"])
    for finding in result["findings"]:
        assert isinstance(finding["line"], int)
        assert "extra" in finding and isinstance(finding["extra"], dict)

    by_line = {f["line"]: f for f in result["findings"]}
    # pinned against fixtures/sample_project/answer-key.md, not just schema membership
    assert by_line[2]["bucket"] == "critical"  # inner
    assert by_line[2]["category"] == "low-coverage"
    assert by_line[17]["bucket"] == "hotspot"  # uncovered_fn
    assert by_line[17]["category"] == "low-coverage"


def test_bucket_gate_is_the_classic_30_boundary():
    assert audit._bucket(29.999) == "hotspot"
    assert audit._bucket(30.0) == "critical"
    assert audit._bucket(15.0) == "hotspot"


def test_category_dominant_ingredient_boundary():
    # complexity=4: penalty >= complexity when coverage <= 0 (penalty=64 at cov=0)
    assert audit._category(4, 0.0) == "low-coverage"
    # complexity=4, coverage=1.0 -> penalty=0 < complexity=4
    assert audit._category(4, 1.0) == "high-complexity"


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


def test_under_floor_sample_caps_at_five_not_the_full_count():
    """Regression witness: with more under-floor rows than the cap, the
    sample must stay capped -- the fixture only has 3 under-floor rows, too
    few for `sample[:N]` to ever bind, so raising the cap left the
    fixture-driven test green with no cap at all.

    Both the input size and the expected sample size are literals on
    purpose. Sizing either off `audit.UNDER_FLOOR_SAMPLE` makes the
    assertion true for every value of the constant, which is how the first
    version of this test still passed with the cap set to 100000."""
    assert audit.UNDER_FLOOR_SAMPLE == 5
    rows = [
        {"file": "m.py", "name": f"clean_{i}", "line": i, "complexity": 1,
         "statement_coverage": 100.0, "branch_coverage": 100.0}
        for i in range(8)
    ]
    result = audit.score(rows)

    assert result["under_floor"]["count"] == 8
    assert len(result["under_floor"]["sample"]) == 5


def test_recommend_write_tests_when_full_coverage_would_clear_the_gate():
    rec = audit._recommend(6)
    assert rec == {"action": "write tests", "projected_crap": 6.0}
    assert audit._crap(6, 1.0) == 6


def test_recommend_refactor_when_complexity_alone_meets_or_exceeds_the_gate():
    """Complexity >= the classic gate (30): no amount of coverage escapes it,
    since full coverage still leaves CRAP == complexity."""
    rec = audit._recommend(30)
    assert rec == {"action": "refactor", "projected_crap": 30.0}
    rec = audit._recommend(35)
    assert rec == {"action": "refactor", "projected_crap": 35.0}


def test_findings_carry_a_recommendation_in_extra():
    """AC: findings.jsonl rows gain a recommendation without losing any
    existing extra field -- schema-compatible extension, not a breaking change."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)
    by_line = {f["line"]: f for f in result["findings"]}

    inner = by_line[2]
    for field in ("complexity", "statement_coverage", "branch_coverage", "coverage", "crap"):
        assert field in inner["extra"], field
    assert inner["extra"]["recommendation"] == {"action": "write tests", "projected_crap": 6.0}

    uncovered_fn = by_line[17]
    assert uncovered_fn["extra"]["recommendation"] == {"action": "write tests", "projected_crap": 4.0}


def test_gate_suggestions_present_and_correct():
    """AC5: both suggested gate values are present and correct for the fixture."""
    radon_json, coverage_json = _load_fixture()
    rows = audit.normalize(radon_json, coverage_json)
    result = audit.score(rows)

    assert result["gates"]["classic"] == 30
    assert result["gates"]["above_current_max"] == 33


def test_cli_main_prints_whole_score_result():
    """The thin CLI main reads the two JSON files and prints the whole
    score() result -- findings, under_floor, gates, and ranking -- as one
    JSON object."""
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
    result = json.loads(out)
    assert set(result) == {"findings", "under_floor", "gates", "ranking"}
    assert len(result["findings"]) == 2
    assert {row["file"] for row in result["findings"]} == {"sample.py"}
    assert {row["line"] for row in result["findings"]} == {2, 17}


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


def test_normalize_ts_branch_axis_lands_on_branch_not_statement():
    """Regression witness: the `kind == "branch"` arm must put the measured
    `cov` in branch_coverage and the synthetic 100.0 in statement_coverage,
    not the reverse -- with the fixture's only asymmetric branch row
    (`inner`, cov=20), swapping the two assignments changes both fields, so
    this fails if they're ever transposed."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    by_name = {r["name"]: r for r in rows}

    inner = by_name["inner"]
    assert inner["branch_coverage"] == 20.0
    assert inner["statement_coverage"] == 100.0


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
            "coverage_axis": "both",
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
    _assert_findings_schema(result["findings"])


def _assert_axis_nulled(row, measured_axis, measured_value):
    """The one home for the synthetic-axis-nulling assertion: whichever axis
    normalize_ts actually measured keeps its value, the other reads None —
    never the synthetic 100.0 filler `score()`'s min() ignores. Shared by
    the findings-extra and ranking-row variants of the same check."""
    axes = {"statement_coverage", "branch_coverage"}
    assert row[measured_axis] == measured_value
    unmeasured = (axes - {measured_axis}).pop()
    assert row[unmeasured] is None


def test_ts_findings_never_report_the_synthetic_unmeasured_axis():
    """P1 fix: normalize_ts fills the non-dominant axis with a synthetic
    100.0 so score()'s min() ignores it -- that number must never leak into
    a finding's extra as if it were measured."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    result = audit.score(rows)
    by_name = {f["file"] + ":" + str(f["line"]): f for f in result["findings"]}

    _assert_axis_nulled(by_name["src/sample.ts:2"]["extra"], "branch_coverage", 20.0)
    _assert_axis_nulled(by_name["src/sample.ts:23"]["extra"], "statement_coverage", 0.0)


def test_ts_ranking_never_reports_the_synthetic_unmeasured_axis():
    """P2 fix: ranking.jsonl carries every row, not just findings -- the
    synthetic 100.0 filler must be nulled there too, not only in the
    findings extra. Otherwise ranking.jsonl (which score() emits verbatim
    as the calibration asset) leaks a fabricated coverage percentage."""
    report = _load_ts_fixture()
    rows = audit.normalize_ts(report)
    result = audit.score(rows)
    by_name = {r["name"]: r for r in result["ranking"]}

    _assert_axis_nulled(by_name["inner"], "branch_coverage", 20.0)
    _assert_axis_nulled(by_name["uncoveredFn"], "statement_coverage", 0.0)


def test_cli_main_ts_mode_prints_whole_score_result():
    """The thin CLI's `--ts <report.json>` mode reads the captured tool
    report and prints the whole score() result -- findings, under_floor,
    gates, and ranking -- as one JSON object."""
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
    result = json.loads(out)
    assert set(result) == {"findings", "under_floor", "gates", "ranking"}
    assert len(result["findings"]) == 2
    assert {row["file"] for row in result["findings"]} == {"src/sample.ts"}


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
