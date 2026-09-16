#!/usr/bin/env python3
"""Tests for the review-axis tally script (#854). Seams: filename parsing,
repo/round-kind folding, and the round-1<->verify<->PR join — the mechanical
scaffolding around the LLM classification pass, same convention as
burndown/phases_test.py (plain test_* functions, no pytest)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tally_review_axes as t


def test_parses_plain_round1_report():
    r = t.parse_report_filename("review-standards-790.md")
    assert r.kind == "round1"
    assert r.axes == ("standards",)
    assert r.issue == 790


def test_parses_combined_verify_report():
    r = t.parse_report_filename("review-verify-736.md")
    assert r.kind == "verify"
    assert r.axes == ("standards", "spec", "correctness")
    assert r.issue == 736


def test_verification_is_the_same_kind_as_verify():
    r = t.parse_report_filename("review-verification-817.md")
    assert r.kind == "verify"
    assert r.axes == ("standards", "spec", "correctness")
    assert r.issue == 817


def test_parses_axis_specific_verify_report():
    r = t.parse_report_filename("review-correctness-368-verify.md")
    assert r.kind == "verify"
    assert r.axes == ("correctness",)
    assert r.issue == 368


def test_parses_the_790_standards_spec_verify_anomaly():
    r = t.parse_report_filename("review-standards-spec-790-verify.md")
    assert r.kind == "verify"
    assert r.axes == ("standards", "spec")
    assert r.issue == 790


def test_rejects_an_unparseable_filename():
    assert t.parse_report_filename("mutate.py") is None
    assert t.parse_report_filename("diff-425.patch") is None
    assert t.parse_report_filename("verify-790-dispositions.md") is None


def test_folds_agent_skills_and_skills_into_one_repo():
    assert t.fold_repo("skills") == "skills"
    assert t.fold_repo("agent-skills") == "skills"
    assert t.fold_repo("sudokumaker-custom-constraints") == "sudokumaker-custom-constraints"
    assert t.fold_repo("twitch-rules-scroller") == "twitch-rules-scroller"


def test_join_groups_round1_and_verify_reports_by_issue():
    reports = [
        ("skills", "review-standards-736.md"),
        ("skills", "review-spec-736.md"),
        ("skills", "review-correctness-736.md"),
        ("skills", "review-verify-736.md"),
        ("agent-skills", "review-standards-761.md"),
    ]
    index = t.build_issue_index(reports)
    assert set(index.keys()) == {("skills", 736), ("skills", 761)}
    entry = index[("skills", 736)]
    assert sorted(entry["round1"].keys()) == ["correctness", "spec", "standards"]
    assert len(entry["verify"]) == 1


def test_join_attaches_matched_pr_number():
    reports = [("skills", "review-standards-736.md")]
    index = t.build_issue_index(reports)
    issue_to_pr = {"skills": {736: [769]}}
    t.attach_prs(index, issue_to_pr)
    assert index[("skills", 736)]["pr"] == 769


def test_join_leaves_pr_none_when_unmatched():
    reports = [("twitch-rules-scroller", "review-standards-274.md")]
    index = t.build_issue_index(reports)
    t.attach_prs(index, {"twitch-rules-scroller": {}})
    assert index[("twitch-rules-scroller", 274)]["pr"] is None


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
