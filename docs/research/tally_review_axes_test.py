#!/usr/bin/env python3
"""Tests for the review-axis tally script (#854). Seams: filename parsing,
repo/round-kind folding, the round-1<->verify<->PR join (including the
issue<->PR matcher that used to be ad hoc, per round-1 review finding P1),
and the mechanical guards (missing cache dir, malformed override file,
round-1 axis conflicts) — the scaffolding around the LLM classification
pass, same convention as burndown/phases_test.py (plain test_* functions,
no pytest)."""
import contextlib
import io
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
    # (_AXIS_VERIFY_RE); a single axis is just the n=1 case of its
    # `axis(-axis)*` group. Round-1 review S1/S2: a second, unreachable
    # regex used to sit ahead of this in the source with a test that
    # stayed green even if that branch were deleted. Now there is only
    # one implementation, so this test is a real witness of it.
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


def test_parses_a_findings_sidecar_filename():
    assert t.parse_finding_sidecar_filename("findings-standards-855.jsonl") == ("standards", 855)
    assert t.parse_finding_sidecar_filename("findings-correctness-1.jsonl") == ("correctness", 1)
    assert t.parse_finding_sidecar_filename("review-standards-855.md") is None
    assert t.parse_finding_sidecar_filename("dispositions-855.jsonl") is None


def test_parses_a_dispositions_sidecar_filename():
    assert t.parse_disposition_sidecar_filename("dispositions-855.jsonl") == 855
    assert t.parse_disposition_sidecar_filename("findings-standards-855.jsonl") is None


def test_parses_a_valid_finding_line():
    f = t.parse_finding_line(json.dumps({
        "id": "S1", "axis": "standards", "severity": "hard",
        "file": "foo.py", "title": "mysterious name",
    }))
    assert f == t.Finding(id="S1", axis="standards", severity="hard", file="foo.py", title="mysterious name")


def test_finding_line_rejects_malformed_json_without_raising():
    # a partial write costs one line, not the file (#855) — the parser
    # must return None, never raise, on a truncated or malformed line.
    assert t.parse_finding_line("{not valid json") is None


def test_finding_line_rejects_an_invalid_severity():
    bad = json.dumps({"id": "S1", "axis": "standards", "severity": "critical",
                       "file": "foo.py", "title": "x"})
    assert t.parse_finding_line(bad) is None


def test_finding_line_rejects_a_missing_field():
    bad = json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "foo.py"})
    assert t.parse_finding_line(bad) is None


def test_parses_a_valid_fixed_disposition_line():
    d = t.parse_disposition_line(json.dumps({"id": "S1", "outcome": "fixed", "sha": "abc123"}))
    assert d == t.Disposition(id="S1", outcome="fixed", detail="abc123")


def test_parses_a_valid_disputed_disposition_line():
    d = t.parse_disposition_line(json.dumps({"id": "S2", "outcome": "disputed", "reason": "not a real issue"}))
    assert d == t.Disposition(id="S2", outcome="disputed", detail="not a real issue")


def test_parses_a_valid_filed_disposition_line():
    d = t.parse_disposition_line(json.dumps({"id": "S3", "outcome": "filed", "ticket": 900}))
    assert d == t.Disposition(id="S3", outcome="filed", detail="900")


def test_disposition_line_rejects_missing_detail_field():
    # outcome says "fixed" but the sha the outcome requires is absent
    bad = json.dumps({"id": "S1", "outcome": "fixed"})
    assert t.parse_disposition_line(bad) is None


def test_disposition_line_rejects_malformed_json_without_raising():
    assert t.parse_disposition_line("{not valid json") is None


def test_find_sidecar_files_finds_both_kinds_and_skips_scratch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text("")
        (root / "skills" / "dispositions-1.jsonl").write_text("")
        (root / "skills" / "review-standards-1.md").write_text("x")
        (root / "scratch-1").mkdir()
        (root / "scratch-1" / "findings-standards-2.jsonl").write_text("")
        found = t.find_sidecar_files(root)
        assert set(found) == {
            ("skills", "findings-standards-1.jsonl"),
            ("skills", "dispositions-1.jsonl"),
        }


def test_tally_sidecars_rolls_findings_and_dispositions_into_a_table():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-855.jsonl").write_text("\n".join([
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"}),
            json.dumps({"id": "S2", "axis": "standards", "severity": "judgement", "file": "b.py", "title": "y"}),
            json.dumps({"id": "S3", "axis": "standards", "severity": "judgement", "file": "c.py", "title": "z"}),
        ]))
        (root / "skills" / "dispositions-855.jsonl").write_text("\n".join([
            json.dumps({"id": "S1", "outcome": "fixed", "sha": "abc123"}),
            json.dumps({"id": "S2", "outcome": "disputed", "reason": "no"}),
        ]))
        table = t.tally_sidecars(root)
        assert table["skills/standards"] == {
            "raised": 3, "fixed": 1, "disputed": 1, "filed": 0, "undisposed": 1,
        }


def test_tally_sidecars_keys_a_disposition_to_its_own_repo_and_issue():
    # a disposition in one repo/issue must never resolve a same-id finding
    # filed under a different repo or issue (#855, round-1 correctness C4:
    # the old fixture only varied repo, leaving the issue half of the key
    # unwitnessed — this now checks both independently).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "other").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text(
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"})
        )
        (root / "other" / "dispositions-1.jsonl").write_text(
            json.dumps({"id": "S1", "outcome": "fixed", "sha": "abc"})
        )
        # same repo as the finding, but a different issue: must not resolve either.
        (root / "skills" / "dispositions-2.jsonl").write_text(
            json.dumps({"id": "S1", "outcome": "fixed", "sha": "abc"})
        )
        table = t.tally_sidecars(root)
        assert table["skills/standards"]["undisposed"] == 1
        assert table["skills/standards"]["fixed"] == 0


def test_tally_sidecars_survives_one_malformed_line_in_a_real_file():
    # round-1 standards S4: the file-level guarantee ("a partial write
    # costs one line, not the file") had no witness through tally_sidecars
    # itself — only through the line-parser functions directly.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text("\n".join([
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"}),
            "{not valid json, a truncated write",
            json.dumps({"id": "S2", "axis": "standards", "severity": "judgement", "file": "b.py", "title": "y"}),
        ]))
        table = t.tally_sidecars(root)
        assert table["skills/standards"]["raised"] == 2


def test_tally_sidecars_skips_one_undecodable_file_without_losing_the_rest():
    # round-1 correctness C1: a sidecar truncated mid multibyte character
    # used to raise UnicodeDecodeError out of read_text() and kill the
    # entire tally, losing every other repo/axis's numbers too.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_bytes(b"\xff\xfe" + b"garbage")
        (root / "skills" / "findings-correctness-2.jsonl").write_text(
            json.dumps({"id": "C1", "axis": "correctness", "severity": "hard", "file": "a.py", "title": "x"})
        )
        table = t.tally_sidecars(root)
        assert table["skills/correctness"]["raised"] == 1
        assert "skills/standards" not in table


def test_tally_sidecars_raises_on_a_duplicate_finding_id_in_one_file():
    # round-1 correctness C2: two lines sharing an id in the same
    # findings-*.jsonl file used to silently collapse to one, undercounting
    # `raised` with no signal that anything was lost.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text("\n".join([
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"}),
            json.dumps({"id": "S1", "axis": "standards", "severity": "judgement", "file": "b.py", "title": "y"}),
        ]))
        try:
            t.tally_sidecars(root)
            assert False, "expected a ValueError on the duplicate finding id"
        except ValueError as e:
            assert "S1" in str(e)


def test_tally_sidecars_raises_on_a_duplicate_id_across_the_repo_alias_fold():
    # round-1 correctness C3: the same collision, reached via fold_repo —
    # `agent-skills` and `skills` fold to one repo name, so a same-id
    # finding for the same issue under both directory names must not
    # silently erase one.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "agent-skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text(
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"})
        )
        (root / "agent-skills" / "findings-standards-1.jsonl").write_text(
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"})
        )
        try:
            t.tally_sidecars(root)
            assert False, "expected a ValueError on the cross-alias duplicate id"
        except ValueError as e:
            assert "S1" in str(e)


def test_tally_sidecars_uses_the_filename_axis_over_a_mismatched_line_axis():
    # round-1 standards S2 / spec axis: parse_finding_sidecar_filename's
    # axis was discarded in favor of each line's own `axis` field, so a
    # line with a wrong `axis` value silently tallied under the wrong
    # axis. The filename — which axis wrote this file — is authoritative.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text(
            json.dumps({"id": "S1", "axis": "spec", "severity": "hard", "file": "a.py", "title": "x"})
        )
        table = t.tally_sidecars(root)
        assert table["skills/standards"]["raised"] == 1
        assert "skills/spec" not in table


def test_tally_sidecars_warns_on_an_orphan_disposition():
    # round-1 correctness C4: a disposition whose id matches no finding
    # used to vanish with no signal — the table just shows undisposed
    # counts that don't add up to what the prose says was dispositioned.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills").mkdir()
        (root / "skills" / "findings-standards-1.jsonl").write_text(
            json.dumps({"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "x"})
        )
        (root / "skills" / "dispositions-1.jsonl").write_text(
            json.dumps({"id": "S9", "outcome": "fixed", "sha": "abc"})
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            t.tally_sidecars(root)
        err = stderr.getvalue()
        assert "S9" in err
        assert "orphan" in err


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
