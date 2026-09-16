#!/usr/bin/env python3
"""Tests for the review-axis tally script (#854). Seams: filename parsing,
repo/round-kind folding, the round-1<->verify<->PR join (including the
issue<->PR matcher that used to be ad hoc, per round-1 review finding P1),
and the mechanical guards (missing cache dir, malformed override file,
round-1 axis conflicts) — the scaffolding around the LLM classification
pass, same convention as burndown/phases_test.py (plain test_* functions,
no pytest)."""
import json
import os
import sys
import tempfile
from pathlib import Path

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
    # There is exactly one regex path for a `-verify.md` filename
    # (_MULTI_AXIS_VERIFY_RE); a single axis is just the n=1 case of its
    # `axis(-axis)*` group. Round-1 review S1/S2: a second, unreachable
    # regex (_AXIS_VERIFY_RE) used to sit ahead of this in the source with
    # a test that stayed green even if that branch were deleted. Now there
    # is only one implementation, so this test is a real witness of it.
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


def test_join_raises_on_a_round1_axis_conflict():
    # round-1 review C6: if `agent-skills` and `skills` (folded to the same
    # repo) ever produced a same-named axis report for the same issue, the
    # old code silently overwrote one with the other. That must now fail
    # loudly instead of silently losing data.
    reports = [
        ("skills", "review-standards-736.md"),
        ("agent-skills", "review-standards-736.md"),
    ]
    try:
        t.build_issue_index(reports)
        assert False, "expected a ValueError on the round-1 axis conflict"
    except ValueError as e:
        assert "736" in str(e)
        assert "standards" in str(e)


def test_normalize_issue_to_pr_converts_string_keys_to_int():
    # json.loads always hands back string keys; production data is never
    # int-keyed. This is the one real path attach_prs should walk.
    raw = {"skills": {"736": [769], "761": [800]}}
    norm = t.normalize_issue_to_pr(raw)
    assert norm == {"skills": {736: [769], 761: [800]}}


def test_join_attaches_matched_pr_number():
    reports = [("skills", "review-standards-736.md")]
    index = t.build_issue_index(reports)
    issue_to_pr = t.normalize_issue_to_pr({"skills": {"736": [769]}})
    t.attach_prs(index, issue_to_pr)
    assert index[("skills", 736)]["pr"] == 769


def test_join_leaves_pr_none_when_unmatched():
    reports = [("twitch-rules-scroller", "review-standards-274.md")]
    index = t.build_issue_index(reports)
    t.attach_prs(index, t.normalize_issue_to_pr({"twitch-rules-scroller": {}}))
    assert index[("twitch-rules-scroller", 274)]["pr"] is None


def test_match_issue_to_prs_uses_a_closes_keyword():
    prs = [{"number": 769, "title": "x", "body": "Closes #736\n\nstuff", "headRefName": "fix-cleanup"}]
    matched = t.match_issue_to_prs(prs, {736})
    assert matched == {736: [769]}


def test_match_issue_to_prs_falls_back_to_branch_name():
    # round-1 review P1: gh's closingIssuesReferences came back empty for
    # nearly every PR in this dataset even when the body said "Closes #N",
    # so the real matcher has to fall back to the implement-<n>/issue-<n>
    # branch-name convention this lane uses.
    prs = [{"number": 795, "title": "no numeral here", "body": "no keyword either", "headRefName": "implement-790"}]
    matched = t.match_issue_to_prs(prs, {790})
    assert matched == {790: [795]}


def test_match_issue_to_prs_ignores_unrelated_prs():
    prs = [{"number": 1, "title": "unrelated", "body": "", "headRefName": "implement-999"}]
    matched = t.match_issue_to_prs(prs, {736})
    assert matched == {}


def test_find_report_files_skips_any_scratch_prefixed_dir():
    # round-1 review C5: the old filter checked for an exact "scratch"
    # path component, so a real dir like "scratch-421" (which exists in
    # the live cache) would NOT be skipped the moment it held a
    # review-*.md file. Use a "scratch-421"-shaped dir here to pin the fix.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "review-standards-1.md").write_text("x")
        (root / "scratch-421").mkdir()
        (root / "scratch-421" / "review-standards-2.md").write_text("x")
        found = t.find_report_files(root)
        assert found == [("skills", "review-standards-1.md")]


def test_find_report_files_uses_the_relative_path_not_the_basename():
    # round-1 review S4: same-named dirs at different depths must not
    # silently merge into one repo bucket.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "review-standards-1.md").write_text("x")
        nested = root / "nested" / "skills"
        nested.mkdir(parents=True)
        (nested / "review-standards-2.md").write_text("x")
        found = t.find_report_files(root)
        # the nested "skills" dir is not a real repo bucket under our
        # cache layout (one level deep only) — it must not be silently
        # folded into the top-level "skills" bucket.
        assert ("skills", "review-standards-1.md") in found
        assert ("skills", "review-standards-2.md") not in found


def test_find_report_files_raises_a_clear_error_on_a_missing_cache_dir():
    # round-1 review C7: a missing cache dir used to silently print
    # "0 files" and exit 0.
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist"
        try:
            t.find_report_files(missing)
            assert False, "expected FileNotFoundError"
        except FileNotFoundError as e:
            assert str(missing) in str(e)


def test_load_issue_to_pr_override_raises_a_clear_error_on_malformed_json():
    # round-1 review C7: malformed --issue-to-pr JSON used to raise a bare
    # traceback.
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text("{not valid json")
        try:
            t.load_issue_to_pr_override(bad)
            assert False, "expected a ValueError with a clear message"
        except ValueError as e:
            assert "bad.json" in str(e)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
