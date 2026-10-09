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
