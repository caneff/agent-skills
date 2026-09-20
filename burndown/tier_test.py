#!/usr/bin/env python3
"""Tests for the exploration pass's ticket tagger (#898). The seam the ticket
names is `(candidate) -> labels to write`: `labels_to_write(candidate)`, and
the tagging pass over a whole candidate set that reports what it wrote.

The three fixtures the ticket asks for are a docs-only candidate with no
label, a docs-only candidate that already has one, and a mixed diff touching
code. The rest guard the direction of the error: a candidate the classifier
cannot read as prose is never labelled, because a wrong `documentation` label
sends a code change down the light tier and it lands with no PR and no
reviewer.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import closure as C  # noqa: E402
import tier as T  # noqa: E402

TIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tier.py")


def candidate(number, files, labels=()):
    return {"number": number, "files": list(files), "labels": list(labels)}


def test_docs_only_candidate_with_no_label_gets_documentation():
    c = candidate(371, ["docs/research/2026-09-14-codex-review-trial.md"])
    assert T.labels_to_write(c) == ["documentation"]


def test_docs_only_candidate_that_already_has_the_label_gets_nothing():
    """Nothing to write is not the same as nothing to say: the label is
    already there, so the pass writes no label and the run reports none."""
    c = candidate(371, ["docs/research/note.md"], ["documentation"])
    assert T.labels_to_write(c) == []


def test_a_mixed_diff_touching_code_gets_nothing():
    """The rule that decides the tier, in the direction that matters. One
    code file among the targets and the candidate is not docs-only, however
    much prose sits beside it — `flow/claude/WORKFLOW.md` § Gate 2: a mixed
    diff is code."""
    c = candidate(451, ["burndown/references/tier.md", "burndown/tier.py"])
    assert T.labels_to_write(c) == []


def test_a_skill_body_is_code_however_the_extension_reads():
    """`SKILL.md` is Markdown and is not prose: its body changes what every
    later session does, which is why § Gate 2 names a skill's `SKILL.md` as
    code. Anywhere in the tree, at any depth."""
    c = candidate(700, ["burndown/SKILL.md"])
    assert T.labels_to_write(c) == []
    assert T.labels_to_write(candidate(700, ["SKILL.md"])) == []


def test_an_unrecognised_extension_is_code():
    """The whitelist direction, stated as a test. A `.json`, a file with no
    extension, a `.py` under `docs/research/` — none of them read as prose
    here, so none of them earns a light tier. Deliberately stricter than
    § Gate 2's research-scripts carve-out: `references/tier.md` § Divergence
    says why, and `tests/all.sh` discovering `*_test.py` anywhere is the
    evidence."""
    for path in ("flow/lane/Cargo.toml", "settings.json", "Makefile",
                 "docs/research/probe.py", "docs/research/2026-09-14.md.bak"):
        assert T.labels_to_write(candidate(1, [path])) == [], path


def test_a_candidate_naming_no_files_is_never_labelled():
    """`all()` over an empty list is True, so the natural spelling of
    "every file is prose" says yes about a candidate whose files nobody
    resolved. A candidate with nothing to read is unknown, and unknown goes
    heavy."""
    assert T.labels_to_write(candidate(1, [])) == []


class FakeGh:
    """Every `gh` argv the pass ran, and nothing else. A writer is tested by
    what it invokes: there is no tracker here to read a label back off."""

    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        return ""


def test_the_pass_writes_the_missing_label_and_only_that():
    gh = FakeGh()
    written = T.tag("caneff/agent-skills", [
        candidate(371, ["docs/research/note.md"]),
        candidate(372, ["docs/research/other.md"], ["documentation"]),
        candidate(373, ["burndown/tier.py"]),
    ], run=gh)
    assert written == [{"number": 371, "labels": ["documentation"]}], written
    assert gh.calls == [["issue", "edit", "371", "--repo", "caneff/agent-skills",
                         "--add-label", "documentation"]], gh.calls


def test_the_pass_never_removes_a_label():
    """The rule stated as a test rather than as a comment: no argv this pass
    builds may carry `--remove-label`, whatever the candidate looks like."""
    gh = FakeGh()
    T.tag("caneff/agent-skills", [
        candidate(371, ["docs/research/note.md"]),
        candidate(372, ["docs/research/other.md"], ["documentation"]),
        candidate(373, ["burndown/tier.py"], ["documentation"]),
    ], run=gh)
    assert all("--remove-label" not in call for call in gh.calls), gh.calls


def test_dry_run_decides_the_same_and_writes_nothing():
    gh = FakeGh()
    written = T.tag("caneff/agent-skills",
                    [candidate(371, ["docs/research/note.md"])],
                    run=gh, write=False)
    assert written == [{"number": 371, "labels": ["documentation"]}], written
    assert gh.calls == [], gh.calls


def test_the_report_names_every_label_written():
    report = T.render([{"number": 371, "labels": ["documentation"]},
                       {"number": 372, "labels": ["documentation"]}])
    assert "#371" in report and "#372" in report
    assert report.count("documentation") == 2, report


def test_the_report_says_so_when_it_wrote_nothing():
    """A run that wrote no label has to say that in words: a report with no
    line about labels reads the same as a report from a pass that never
    ran."""
    assert "no labels written" in T.render([])


class FakeView:
    """`gh issue view --json labels` for a fixed tracker."""

    def __init__(self, labels_by_number):
        self.labels = labels_by_number
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        number = int(args[2])
        names = [{"name": n} for n in self.labels[number]]
        return json.dumps({"labels": names})


def test_a_candidates_labels_come_from_the_tracker_not_the_command_line():
    """The command line names a candidate and its files; whether the label is
    already there is the tracker's answer, read at pass time. A run that
    assumed the label was absent would write it over and over."""
    view = FakeView({371: [], 372: ["documentation", "enhancement"]})
    candidates = T.candidates_from(
        "caneff/agent-skills",
        ["371=docs/research/note.md", "372=docs/a.md,docs/b.md"], run=view)
    assert candidates == [
        {"number": 371, "files": ["docs/research/note.md"], "labels": []},
        {"number": 372, "files": ["docs/a.md", "docs/b.md"],
         "labels": ["documentation", "enhancement"]},
    ], candidates


def test_the_candidate_grammar_is_closures_own():
    """`<n>=<path>[,<path>]...`, read by `closure.parse_candidate` rather
    than a second parser here: the exploration pass hands both readers the
    same candidate strings, and two spellings of that grammar are two places
    for it to drift."""
    view = FakeView({371: []})
    refused = None
    try:
        T.candidates_from("caneff/agent-skills", ["371"], run=view)
    except C.ClosureError as exc:
        refused = exc
    assert refused is not None, "a spec with no files was accepted"
    assert view.calls == [], "the tracker was read for a spec that is not one"


def test_usage_is_an_exit_2_not_a_traceback():
    out = subprocess.run([sys.executable, TIER], capture_output=True, text=True)
    assert out.returncode == 2, out
    assert "usage: tier.py" in out.stderr, out.stderr


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
