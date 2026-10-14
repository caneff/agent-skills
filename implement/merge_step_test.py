"""`implement/SKILL.md` § The merge step 3 reruns the full seam (#1496),
unless the repo's own seam section scopes the run (#1581).

The controller's pre-merge rerun is the only full run a `/implement` merge
outside drain gets, and the worker's own run (§ Review step 3) is narrowed.
So the step must name the full `bash tests/all.sh`, must not narrow it with
`--changed`, and must not keep a skip rule that would drop it whenever the
default branch had not moved. A scope the repo's `AGENTS.md` names for the
change displaces both runs; § Review step 3 states that rule once and step 3
of the merge points at it.

Seam: the Markdown text of review step 3, merge step 3 and the slice
paragraph above it.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def flat(text):
    return " ".join(text.split())


def skill():
    with open(os.path.join(HERE, "SKILL.md")) as f:
        return f.read()


def merge_section():
    text = skill()
    return text[text.index("### The merge"):]


def step3():
    section = merge_section()
    start = section.index("\n3. Merge.")
    end = section.index("\n4. **Answer every outstanding question")
    return section[start:end]


def test_step3_runs_the_full_seam():
    assert "run whole from the merged worktree" in step3()
    assert "`bash tests/all.sh` here" in step3()


def test_step3_does_not_narrow_the_rerun():
    assert "--changed" not in step3()


def test_step3_keeps_no_skip_rule():
    text = step3()
    assert "is-ancestor" not in text
    assert "skip rule" not in text
    assert "only when `<default>` has moved" not in text


def test_slice_paragraph_names_no_skip_test_or_narrowing():
    section = merge_section()
    start = section.index("**The seam rerun starts from")
    bullet = section[start:section.index("- **`closingIssuesReferences`")]
    assert "skip test" not in bullet
    assert "--changed" not in bullet
    assert "origin/spec-<p>" in bullet


def test_step3_records_the_selector_check_around_the_seam():
    text = step3()
    assert "selector_check.py list" in text
    assert "selector_check.py comment" in text
    # the listing is taken before the seam, the comment after it
    assert text.index("selector_check.py list") < text.index("tee ") < text.index("selector_check.py comment")
    for verdict in ("selector: clean", "selector: miss", "selector: hit", "selector: not checked"):
        assert verdict in text


def test_step3_says_the_selector_comment_never_changes_the_merge_decision():
    text = step3()
    assert "evidence only" in text
    assert "a red seam blocks the merge above whatever the" in flat(text)
    assert "no listing and no comment are owed" in flat(text)


def review_step3():
    text = skill()
    start = text.index("3. **Write the dispositions, then run the seam.**")
    return flat(text[start:text.index("#### The Codex pass")])


def test_review_step3_states_the_scope_rule_once_as_a_replacement():
    text = review_step3()
    assert "scopes the run for this kind of change, that scope governs instead of this default" in text
    assert "the default applies only when the section names none" in text


def test_review_step3_says_a_narrowed_line_is_never_a_scope():
    assert "a `**Narrowed**` line is the selector evidence's listing" in review_step3()
    assert "never a scope" in review_step3()


def test_merge_step3_points_at_the_scope_rule_and_bounds_6a_by_it():
    text = flat(step3())
    assert "scope rule of § Review step 3" in text
    assert "ruling 6a's full seam applies only when the section names none" in text
    assert "never skipped, not even when `<default>` has not moved" in text


def test_merge_step3_defines_the_command_as_the_named_scope_else_the_full_seam():
    text = flat(step3())
    assert "is the scope that section names for this kind of change, when it names one; otherwise the command it declares" in text


def test_merge_step3_owes_no_selector_evidence_for_a_scoped_run():
    assert "A run scoped by the repo's own rule (above) is no full run" in flat(step3())


def test_slice_one_suite_run_defers_to_the_repos_scope():
    text = flat(skill())
    start = text.index("as its one suite run, or the scope the repo's `AGENTS.md` names")
    assert "§ Review step 3" in text[start:start + 200]
