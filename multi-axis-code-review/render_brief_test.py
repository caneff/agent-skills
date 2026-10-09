"""render-brief.py (#1216, #1329, #1400): the one source of an axis reviewer's
brief. Seam: the CLI, run against a throwaway worktree directory. Each case
asserts the line it is about, so a render that fails for another reason (a
missing input, a bad path) does not pass for the one under test
(`AGENTS.md` § Recurring defect classes, class 3).
"""
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render-brief.py")
SHAPES = ("an absent or malformed answer read as a benign one",
          "a stated fallback with no mechanism behind it",
          "a test that passes for a reason other than the one it claims")
def render(worktree, diff, *extra, axis="standards", explicit_spec=False):
    args = ["python3", RENDER, "--axis", axis, "--repo", "skills", "--worktree", worktree,
            "--ticket", "1395", "--base", "origin/main", "--diff", diff,
            "--diff-command", "git -C WT diff origin/main...HEAD", "--commit", "abc1234 first commit",
            *extra]
    if axis != "standards" and not {"--spec", "--no-spec"} & set(extra) and not explicit_spec:
        args.append("--no-spec")
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def section(out, heading):
    """The body of a `## heading` section, or None when there is no such heading."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", out, re.M | re.S)
    return m.group(1) if m else None


@pytest.fixture
def wt(tmp_path):
    path = tmp_path / "wt"
    (path / "docs" / "agents").mkdir(parents=True)
    (path / "CODING_STANDARDS.md").write_text("x\n")
    return str(path)


@pytest.fixture
def diff(tmp_path):
    path = tmp_path / "diff.patch"
    path.write_text("diff --git a/f b/f\n" * 7)
    return str(path)


def test_a_minimal_render_succeeds(wt, diff):
    code, _, err = render(wt, diff)
    assert code == 0, err


def test_the_diffs_line_count_is_read_from_the_file_not_asserted(wt, diff):
    _, out, _ = render(wt, diff)
    assert "(7 lines)" in out, out


def test_the_report_filename_is_pinned_once_for_this_axis_and_ticket(wt, diff):
    _, out, _ = render(wt, diff)
    assert out.count("review-standards-1395.md") == 1 and "review-spec" not in out, out


def test_the_sidecar_and_marker_names_are_pinned(wt, diff):
    _, out, _ = render(wt, diff)
    assert "findings-standards-1395.jsonl" in out and "findings-standards-1395.done" in out, out


# #1329: standards sources are listed from the worktree with ls, not asserted.
def test_a_standards_file_present_in_the_worktree_is_listed(wt, diff):
    _, out, _ = render(wt, diff)
    assert "CODING_STANDARDS.md" in (section(out, "Standards sources") or ""), out


def test_a_standards_file_absent_from_the_worktree_is_not_listed(wt, diff):
    _, out, _ = render(wt, diff)
    assert "CONTRIBUTING.md" not in (section(out, "Standards sources") or ""), out


def test_the_domain_glossary_present_in_the_worktree_is_listed_as_glossary(wt, diff):
    open(os.path.join(wt, "GLOSSARY.md"), "w").write("x\n")
    _, out, _ = render(wt, diff)
    assert "GLOSSARY.md" in (section(out, "Standards sources") or ""), out


def test_defect_classes_absent_the_three_shapes_are_inline_and_the_file_is_not_named(wt, diff):
    _, out, _ = render(wt, diff)
    src, dc = section(out, "Standards sources") or "", section(out, "Defect classes") or ""
    assert all(s in dc for s in SHAPES) and "defect-classes.md" not in src, dc


def test_defect_classes_present_is_listed_as_a_source_and_read_by_name(wt, diff):
    open(os.path.join(wt, "docs", "agents", "defect-classes.md"), "w").write("x\n")
    _, out, _ = render(wt, diff)
    src, dc = section(out, "Standards sources") or "", section(out, "Defect classes") or ""
    assert "docs/agents/defect-classes.md" in src and "docs/agents/defect-classes.md" in dc, (src, dc)
    assert not any(s in dc for s in SHAPES), dc


# #1216/#1400: rulings, the worker's choices and claims stay in their own sections.
@pytest.fixture
def judged(wt, diff):
    _, out, _ = render(wt, diff, "--ruling", "RULED-X by Chris", "--choice", "CHOSE-Y by worker",
                       "--claim", "S1: CLAIM-Z the worker says it fixed this")
    return out


def test_a_ruling_is_printed_under_settled_decisions_only(judged):
    assert "RULED-X" in (section(judged, "Settled decisions") or "") and judged.count("RULED-X") == 1, judged


def test_a_workers_choice_is_never_settled_own_section_flagged(judged):
    settled, own = section(judged, "Settled decisions") or "", section(judged, "Worker's own choices") or ""
    assert "CHOSE-Y" in own and "flag" in own.lower() and "CHOSE-Y" not in settled, judged


def test_a_claim_is_printed_under_the_claims_heading_only_as_a_claim_to_check(judged):
    settled, claims = section(judged, "Settled decisions") or "", section(judged, "Claims to check") or ""
    assert "CLAIM-Z" in claims and judged.count("CLAIM-Z") == 1 and "claim" in claims.lower()
    assert "CLAIM-Z" not in settled, judged


def test_no_claims_no_claims_heading(wt, diff):
    _, out, _ = render(wt, diff)
    assert section(out, "Claims to check") is None, out


def test_no_rulings_the_list_says_none_rather_than_vanishing(wt, diff):
    _, out, _ = render(wt, diff)
    assert "settled decisions: none" in (section(out, "Settled decisions") or "").lower(), out


def test_the_renderer_never_emits_an_outcome_of_its_own(wt, diff):
    _, out, _ = render(wt, diff)
    assert not re.search(r'"outcome"|\b(fixed|moved|disputed)\b', out), out


def test_a_claims_own_words_are_the_only_place_an_outcome_word_appears(wt, diff):
    _, out, _ = render(wt, diff, "--claim", "S1: it says fixed", axis="correctness")
    assert len(re.findall(r'\b(fixed|moved|disputed)\b', out)) == 1, out


# #1400: nested agents, worker count and ceiling.
def test_the_brief_forbids_a_nested_subagent(wt, diff):
    _, out, _ = render(wt, diff)
    assert "no nested subagent" in out.lower(), out


def test_default_worker_count_and_wall_clock_ceiling_are_stated(wt, diff):
    _, out, _ = render(wt, diff)
    assert "at most 1 worker" in out and "600 seconds" in out, out


def test_worker_count_and_ceiling_are_taken_from_the_inputs(wt, diff):
    _, out, _ = render(wt, diff, "--workers", "3", "--ceiling", "90")
    assert "at most 3 worker" in out and "90 seconds" in out, out


# #1230: the rating field belongs to the correctness sidecar.
def test_the_correctness_sidecar_schema_carries_rating_confirmed_plausible(wt, diff):
    _, out, _ = render(wt, diff, axis="correctness")
    assert '"rating": "CONFIRMED" or "PLAUSIBLE"' in out, out


def test_the_spec_sidecar_schema_carries_no_rating(wt, diff):
    _, out, _ = render(wt, diff, axis="spec")
    assert '"rating"' not in out, out


# Refusals name their cause and never render a half brief.
def test_a_missing_diff_capture_is_refused_by_name(wt, tmp_path):
    code, out, err = render(wt, str(tmp_path / "nope.patch"))
    assert code == 2 and "nope.patch" in err and not out, err


def test_an_empty_diff_capture_is_refused(wt, tmp_path):
    (tmp_path / "empty.patch").write_text("")
    code, out, err = render(wt, str(tmp_path / "empty.patch"))
    assert code == 2 and "empty" in err and not out, err


def test_a_worktree_that_is_not_a_directory_is_refused(tmp_path, diff):
    code, _, err = render(str(tmp_path / "no-such-dir"), diff)
    assert code == 2 and "no-such-dir" in err, err


def test_an_unknown_axis_is_refused(wt, diff):
    code, _, err = render(wt, diff, axis="docs")
    assert code == 2, err


def test_a_spec_axis_with_neither_spec_nor_no_spec_is_refused(wt, diff):
    code, out, err = render(wt, diff, axis="spec", explicit_spec=True)
    assert code == 2 and "--spec" in err and not out, err


def test_spec_together_with_no_spec_is_refused(wt, diff):
    code, out, err = render(wt, diff, "--spec", "x.md", "--no-spec", axis="correctness")
    assert code == 2 and "both" in err and not out, err


def test_no_spec_renders_no_spec_available(wt, diff):
    code, out, err = render(wt, diff, "--no-spec", axis="correctness")
    assert code == 0 and "no spec available" in out, err


def test_a_claim_with_no_finding_id_is_refused(wt, diff):
    code, _, err = render(wt, diff, "--claim", "no colon here")
    assert code == 2 and "no colon here" in err, err


# #1218: the capture's stat line reaches the prompt.
def test_the_captures_stat_line_is_printed_under_inputs(wt, diff):
    stat = "captured: 3 files; excluded 1 generated file(s): g/x.json"
    _, out, _ = render(wt, diff, "--capture-stat", stat)
    assert stat in (section(out, "Inputs") or ""), out


# #1325/#1324: the worker cap binds the witness check, which has its own concurrency.
def test_the_correctness_prompt_tells_the_witness_check_its_slot_cap(wt, diff):
    _, out, _ = render(wt, diff, "--workers", "2", axis="correctness")
    assert "--slots 2" in out, out


def test_a_prompt_with_no_witness_check_carries_no_slots(wt, diff):
    _, out, _ = render(wt, diff, "--workers", "2")
    assert "--slots" not in out, out


# Each axis renders its own brief, from the one file per axis.
@pytest.mark.parametrize("axis,needle", [("standards", "Over-engineering"), ("spec", "scope creep"),
                                         ("correctness", "witness-check.sh")])
def test_each_axis_brief_is_included(wt, diff, axis, needle):
    _, out, _ = render(wt, diff, axis=axis)
    assert needle in (section(out, "Brief") or ""), out
