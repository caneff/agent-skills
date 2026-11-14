"""Tests for mutation-audit's `plan(repo)` and the counts both parsers stamp."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import audit  # noqa: E402


def _tree(root, files):
    for rel in files:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("x = 1\n")


def test_plan_returns_candidates_no_tests_total_and_siblings(tmp_path):
    root = str(tmp_path)
    _tree(root, ["pkg/widget.py", "pkg/test_widget.py", "pkg/helper.py", "pkg/__init__.py"])
    plan = audit.plan(root)
    assert plan["candidates"] == ["pkg/widget.py"]
    assert plan["no_tests"] == ["pkg/helper.py"]
    assert plan["total"] == 2  # worthy source modules: widget and helper
    assert "pkg/test_widget.py" in plan["siblings"]["pkg/widget.py"]
    assert set(plan["siblings"]) == {"pkg/widget.py"}  # siblings of the candidates only


def test_plan_of_a_repo_with_nothing_testable_is_empty_not_an_error(tmp_path):
    assert audit.plan(str(tmp_path)) == {"candidates": [], "no_tests": [], "total": 0, "siblings": {}}


def test_plan_agrees_with_the_suggest_and_no_tests_commands(tmp_path, capsys):
    root = str(tmp_path)
    _tree(root, ["a.py", "test_a.py", "b.py"])
    audit.main(["audit.py", "--suggest", root])
    assert [json.loads(ln)["candidate"] for ln in capsys.readouterr().out.splitlines()] == ["a.py"]
    audit.main(["audit.py", "--no-tests", root])
    assert json.loads(capsys.readouterr().out) == {"no_tests": ["b.py"], "total": 2}


def test_both_parsers_stamp_the_same_three_counts():
    mutmut = audit.parse_mutmut_results(
        "    m.x_f__mutmut_1: killed\n    m.x_f__mutmut_2: survived\n    m.x_f__mutmut_3: no tests")
    stryker = audit.parse_stryker_report(json.dumps({"files": {"a.js": {"mutants": [
        {"id": "1", "mutatorName": "M", "status": "Killed", "location": {"start": {"line": 1}}},
        {"id": "2", "mutatorName": "M", "status": "Survived", "location": {"start": {"line": 2}}},
        {"id": "3", "mutatorName": "M", "status": "NoCoverage", "location": {"start": {"line": 3}}}]}}}))
    for rows in (mutmut, stryker):
        assert [(r["extra"]["killed_count"], r["extra"]["survived_count"], r["extra"]["no_coverage_count"])
                for r in rows] == [(1, 1, 1)] * 2
