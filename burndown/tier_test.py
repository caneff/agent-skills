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
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile

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


def test_a_documentation_label_on_a_ticket_targeting_code_is_stripped():
    """#1045: #969 targeted a `SKILL.md` and carried `documentation` from its
    filer. The label is a claim; the targets are the evidence, and a code
    target makes the claim wrong."""
    c = candidate(969, ["multi-axis-code-review/SKILL.md"], ["documentation"])
    assert T.labels_to_strip(c) == ["documentation"]
    mixed = candidate(970, ["docs/research/n.md", "burndown/tier.py"], ["documentation"])
    assert T.labels_to_strip(mixed) == ["documentation"]


def test_nothing_is_stripped_from_prose_unlabelled_or_unknown_candidates():
    assert T.labels_to_strip(candidate(1, ["docs/research/n.md"], ["documentation"])) == []
    assert T.labels_to_strip(candidate(2, ["burndown/tier.py"])) == []
    # No resolved files: unknown is not evidence the label is wrong.
    assert T.labels_to_strip(candidate(3, [], ["documentation"])) == []


class FakeGh:
    """Every `gh` argv the pass ran, and nothing else. A writer is tested by
    what it invokes: there is no tracker here to read a label back off."""

    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        return json.dumps({"labels": []}) if args[1] == "view" else ""


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


def test_the_pass_only_ever_raises_the_tier():
    """The rule stated as a test rather than as a comment: the one removal
    this pass makes is `documentation`, from a candidate targeting code. A
    prose candidate, an unknown one, and every other label stay as they are,
    so nothing here sends a ticket from heavy to light."""
    gh = FakeGh()
    stripped = []
    T.tag("caneff/agent-skills", [
        candidate(371, ["docs/research/note.md"]),
        candidate(372, ["docs/research/other.md"], ["documentation", "enhancement"]),
        candidate(373, ["burndown/tier.py"], ["documentation", "enhancement"]),
        candidate(374, [], ["documentation"]),
    ], run=gh, stripped=stripped)
    removals = [c for c in gh.calls if "--remove-label" in c]
    assert removals == [["issue", "edit", "373", "--repo", "caneff/agent-skills",
                         "--remove-label", "documentation"]], gh.calls
    assert stripped == [{"number": 373, "labels": ["documentation"]}], stripped


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


def test_a_dry_run_says_would_write_rather_than_written():
    """A preview that reports a write is worse than no preview: the line is
    the run's record of what the tracker now carries, and a controller
    reading `labels written:` after a dry run would believe the tier was
    already fixed."""
    gh = FakeGh()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["tier.py", "caneff/agent-skills", "371=a.md", "--dry-run"],
                      run=gh)
    assert code == 0, code
    assert "would write:" in out.getvalue(), out.getvalue()
    assert "would strip: none" in out.getvalue(), out.getvalue()
    assert "labels written" not in out.getvalue(), out.getvalue()
    assert "labels stripped" not in out.getvalue(), out.getvalue()
    assert gh.calls == [["issue", "view", "371", "--repo", "caneff/agent-skills",
                         "--json", "labels"]], gh.calls


def test_the_report_says_so_when_it_wrote_nothing():
    """A run that wrote no label has to say that in words: a report with no
    line about labels reads the same as a report from a pass that never
    ran."""
    assert T.render([]) == "labels written: none\nlabels stripped: none"


def test_a_dry_run_previews_the_strip_and_writes_nothing():
    """The strip is previewed the way the add is: `would strip:` names the
    ticket, and no `issue edit` runs."""
    tracker = Tracker({969: ["documentation"]})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["tier.py", "caneff/agent-skills", "969=x/SKILL.md", "--dry-run"],
                      run=tracker)
    assert code == 0, code
    assert "would strip:" in out.getvalue() and "#969" in out.getvalue(), out.getvalue()
    assert all(c[1] == "view" for c in tracker.calls), tracker.calls
    assert tracker.labels[969] == ["documentation"], tracker.labels


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


class Tracker:
    """A tracker that keeps state: `issue view` reads the labels an earlier
    `issue edit` left, so a test can ask what dispatch will read next."""

    def __init__(self, labels_by_number):
        self.labels = {n: list(ls) for n, ls in labels_by_number.items()}
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        number = int(args[2])
        if args[1] == "view":
            return json.dumps({"labels": [{"name": n} for n in self.labels[number]]})
        for flag, value in zip(args, args[1:]):
            for name in value.split(","):
                if flag == "--add-label" and name not in self.labels[number]:
                    self.labels[number].append(name)
                if flag == "--remove-label" and name in self.labels[number]:
                    self.labels[number].remove(name)
        return ""


def test_a_code_candidate_with_a_prose_body_leaves_the_pass_dispatchable_heavy():
    """#1118: dispatch reads only the ticket body's paths, so a body naming
    only prose keeps a filer's `documentation` label through the claim even
    when the clumper's candidate line names a `SKILL.md`. The tagging pass is
    the one reader holding that candidate line, so it removes the label, and
    dispatch — light only on a `documentation` label — sends the ticket heavy.
    The tracker is what dispatch reads, so the tracker is what is asserted."""
    tracker = Tracker({1118: ["documentation", "ready-for-agent"],
                       372: ["documentation", "ready-for-agent"]})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["tier.py", "caneff/agent-skills",
                       "1118=docs/n.md,x/SKILL.md", "372=docs/n.md"], run=tracker)
    assert code == 0, code
    assert "documentation" not in tracker.labels[1118], tracker.labels
    assert tracker.labels[1118] == ["ready-for-agent"], tracker.labels
    # A prose candidate keeps its label: light stays light.
    assert "documentation" in tracker.labels[372], tracker.labels
    assert "labels stripped:" in out.getvalue() and "#1118" in out.getvalue(), out.getvalue()


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
    assert "not a candidate: 371" in str(refused), refused
    assert view.calls == [], "the tracker was read for a spec that is not one"


def test_usage_is_an_exit_2_not_a_traceback():
    out = subprocess.run([sys.executable, TIER], capture_output=True, text=True)
    assert out.returncode == 2, out
    assert "usage: tier.py" in out.stderr, out.stderr


class ExplodingGh:
    """A tracker that answers for a while and then stops. The failure this
    pass has to survive is the third write, not the first: what it already
    put on the tracker is a fact the controller has to be told about."""

    def __init__(self, fails_on):
        self.fails_on = str(fails_on)
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[1] == "view":
            return json.dumps({"labels": []})
        if args[2] == self.fails_on:
            raise T.TierError("'documentation' not found")
        return ""


@contextlib.contextmanager
def only_gh_on_path(script):
    """A `PATH` holding one `gh` — the given shell script — or holding no
    `gh` at all when `script` is None. The error layer is the one part of
    this module a fake cannot reach: every other test injects `run=`."""
    saved = os.environ["PATH"]
    with tempfile.TemporaryDirectory(prefix="tier-path-") as path:
        if script is not None:
            gh_path = os.path.join(path, "gh")
            with open(gh_path, "w") as fh:
                fh.write("#!/bin/sh\n" + script + "\n")
            os.chmod(gh_path, os.stat(gh_path).st_mode | stat.S_IEXEC)
        os.environ["PATH"] = path
        try:
            yield
        finally:
            os.environ["PATH"] = saved


def test_a_failure_midway_still_names_the_labels_already_written():
    """#898: "the run's report names every label the exploration pass wrote".
    A tracker failure on the third candidate must not swallow the record of
    the first two — those labels are on the tracker whatever happens next,
    and a controller that never hears about them cannot act on them."""
    gh = ExplodingGh(fails_on=373)
    written = []
    raised = None
    try:
        T.tag("caneff/agent-skills",
              [candidate(371, ["a.md"]), candidate(372, ["b.md"]),
               candidate(373, ["c.md"]), candidate(374, ["d.md"])],
              run=gh, written=written)
    except T.TierError as exc:
        raised = exc
    assert raised is not None, "the failure was swallowed"
    assert [w["number"] for w in written] == [371, 372], written
    report = T.render(written)
    assert "#371" in report and "#372" in report, report


def test_the_command_line_prints_that_partial_report_before_it_exits():
    """The seam above is only worth having if `main` reaches it: the partial
    report goes to stdout, the failure to stderr, and the exit code is still
    a failure."""
    gh = ExplodingGh(fails_on=372)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = T.main(["tier.py", "caneff/agent-skills", "371=a.md", "372=b.md"],
                      run=gh)
    assert code == 1, code
    assert "#371" in out.getvalue(), out.getvalue()
    assert "'documentation' not found" in err.getvalue(), err.getvalue()


def test_a_failing_gh_is_refused_rather_than_read_as_a_write():
    """The guard that keeps a failed `gh issue edit` from passing for a label
    that landed. Run against a real `gh` on `PATH`, because every other test
    here injects `run=` and never reaches this function."""
    with only_gh_on_path("exit 4"):
        raised = None
        try:
            T.gh(["issue", "edit", "1"])
        except T.TierError as exc:
            raised = exc
        assert raised is not None, "a non-zero gh exit passed for a write"
        assert "issue edit 1" in str(raised), raised


def test_no_gh_at_all_is_refused_too():
    """Otherwise a box without `gh` reports `labels written: none` and every
    docs-only ticket in the queue goes heavy with nobody told why."""
    with only_gh_on_path(None):
        raised = None
        try:
            T.gh(["issue", "edit", "1"])
        except T.TierError as exc:
            raised = exc
        assert raised is not None, "a missing gh passed for a write"
        assert "gh" in str(raised), raised


def test_unreadable_json_from_the_tracker_is_refused():
    """An unreadable answer is not an empty label list: read as one, the pass
    writes the label onto a ticket that may already carry it, every tick."""
    raised = None
    try:
        T.fetch_labels("caneff/agent-skills", 1, run=lambda args: "{not json")
    except T.TierError as exc:
        raised = exc
    assert raised is not None, "unreadable JSON passed for an unlabelled ticket"
    assert "unreadable JSON" in str(raised), raised


def test_an_unknown_flag_is_usage_not_a_candidate():
    """`tier.py <repo> --help` reached the candidate parser and exited 1 with
    "not a candidate: --help". `--strip` is retired (#1118): the pass strips
    itself, and an old report-only call must not run the writing pass."""
    for flag in ("--help", "--strip"):
        out = subprocess.run([sys.executable, TIER, "caneff/agent-skills", "1=a.md", flag],
                             capture_output=True, text=True)
        assert out.returncode == 2, (flag, out)
        assert "usage: tier.py" in out.stderr, out.stderr


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
