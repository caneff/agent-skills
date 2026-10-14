"""`implement/SKILL.md` § The merge step 3 reruns the full seam (#1496).

The controller's pre-merge rerun is the only full run a `/implement` merge
outside drain gets, and the worker's own run (§ Review step 3) is narrowed.
So the step must name the full `bash tests/all.sh`, must not narrow it with
`--changed`, and must not keep a skip rule that would drop it whenever the
default branch had not moved.

Seam: the Markdown text of step 3 and of the slice paragraph above it.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


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
    assert "a red seam blocks the merge above whatever the" in text.replace("\n   ", " ")
    assert "no listing and no comment are owed" in text.replace("\n   ", " ")


def flat(text):
    return " ".join(text.split())


def review_step3():
    text = skill()
    start = text.index("3. **Write the dispositions, then run the seam.**")
    return text[start:text.index("#### The Codex pass")]


def test_review_step3_defers_to_the_repos_seam_scope_for_the_change():
    text = flat(review_step3())
    assert "scopes the run for this kind of change" in text
    assert "that scope governs" in text
    assert "names none" in text


def test_merge_step3_defers_to_the_repos_seam_scope_for_the_change():
    text = flat(step3())
    assert "scopes the run for this kind of change" in text
    assert "that scope is the run" in text
    assert "names none" in text


def test_merge_step3_no_longer_reads_ruling_6a_as_unconditional():
    text = flat(step3())
    assert "#1581" in text
    assert "never skipped, not even when `<default>` has not moved" in text
    # the default stays unconditional; only a repo-named scope displaces it
    assert "`<default>` has not moved" in text
