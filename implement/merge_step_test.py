"""`implement/SKILL.md` runs one per-change command at every step that tests a
change: the one `selector_check.py command` prints from the repo's own seam
section (#1593), unless that section scopes the run for the change (#1581).

§ Review step 3 (the worker's run), the slice paragraph (a slice's run) and
§ The merge step 3 (the controller's run on the PR merged into current
`<default>`) all run what the resolver prints, and none names `tests/all.sh`:
a hard-coded command is a command some repo does not have (#1590). Merge step
3 runs no full seam: the nightly backstop is the only full run (#1592). Its
`selector:` comment records the listing and judges nothing. A scope the
repo's `AGENTS.md` names for the change displaces the run; § Review step 3
states that rule once and step 3 of the merge points at it.

Seam: the Markdown text of review step 3, merge step 3 and the slice
paragraphs.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESOLVER = "selector_check.py command"


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


def review_step3():
    text = skill()
    start = text.index("3. **Write the dispositions, then run the seam.**")
    return flat(text[start:text.index("#### The Codex pass")])


def slice_paragraph():
    text = skill()
    start = text.index("**A slice runs none of this**")
    return flat(text[start:text.index("**The spec's own review**")])


def slice_merge_bullet():
    section = merge_section()
    start = section.index("**The seam rerun starts from")
    return section[start:section.index("- **`closingIssuesReferences`")]


STEPS = {"review step 3": review_step3, "slice paragraph": slice_paragraph, "merge step 3": step3}


def test_every_step_runs_the_resolvers_output():
    for name, text in STEPS.items():
        assert RESOLVER in text(), name


def test_no_step_hard_codes_a_test_command():
    for name, text in {**STEPS, "slice merge bullet": slice_merge_bullet}.items():
        assert "tests/all.sh" not in text(), name
        assert "--changed" not in text(), name


def test_merge_step3_runs_no_full_seam_per_merge():
    text = flat(step3())
    assert "6a" not in text
    assert "#1496" not in text
    assert "run whole" not in text
    assert "full seam" not in text.replace("runs no full seam", "")
    assert "runs no full seam" in text


def test_merge_step3_runs_on_the_pr_merged_into_current_default_and_merges_only_on_green():
    text = flat(step3())
    assert "git worktree add --detach <absolute path under .scratch/> origin/<default>" in text
    assert "git merge --no-edit <headRefOid>" in text
    assert "The controller merges only on green." in text
    assert "is no longer the sha the seam's worktree was created from, re-run this step" in text


def test_merge_step3_keeps_no_skip_rule():
    text = step3()
    assert "is-ancestor" not in text
    assert "skip rule" not in text


def test_slice_merge_bullet_runs_step3s_command_from_the_spec_branch():
    bullet = flat(slice_merge_bullet())
    assert "skip test" not in bullet
    assert "origin/spec-<p>" in bullet
    assert "full seam" not in bullet


def test_step3_records_the_listing_before_the_run():
    text = step3()
    assert "selector_check.py list" in text
    assert "selector_check.py comment" in text
    assert text.index("selector_check.py list") < text.index("selector_check.py comment") < text.index('sh -c "$cmd"')
    assert "selector: listed <k> suites" in text
    assert "selector: not checked" in text


def test_nothing_at_merge_judges_the_listing():
    text = flat(step3())
    for word in ("clean", "miss", "hit"):
        assert f"selector: {word}" not in text
    assert "judges nothing" in text
    assert "no listing and no comment are owed" in text
    assert "the run's own exit alone decides the merge" in text


def test_a_resolver_refusal_runs_nothing_on_a_guess():
    assert "merge nothing on this step's say-so" in flat(step3())
    assert "run nothing on a guess" in review_step3()


def test_review_step3_states_the_scope_rule_once_as_a_replacement():
    text = review_step3()
    assert "scopes the run for this kind of change, that scope governs instead of this default" in text
    assert "the default applies only when the section names none" in text


def test_review_step3_makes_the_narrowed_line_the_per_change_scope():
    text = review_step3()
    assert "never a scope" not in text
    assert "a `**Narrowed**` line is the per-change command for every change no scope sentence names" in text


def test_merge_step3_points_at_the_scope_rule_once():
    text = flat(step3())
    assert text.count("scope rule of § Review step 3") == 1
    assert "holds here too" not in text
    assert ("a scope the repo's `AGENTS.md` names for this kind of change is the run, in place of the last three "
            "lines; otherwise it is what `selector_check.py command` prints") in text


def test_merge_step3_reads_the_command_from_the_base_not_the_pr():
    # C8: a PR that edits its own seam section must not choose its own gate.
    calls = [x for x in step3().splitlines() if "selector_check.py" in x and "~/.agents" in x]
    assert len(calls) == 3, calls
    for line in calls:
        assert "--rev origin/<default>" in line, line


def test_the_slice_paragraph_states_what_its_verbatim_command_selects():
    # P6, ruled: the slice runs the command verbatim, and says it is wider, never narrower.
    assert "never a narrower one" in slice_paragraph()


def test_merge_step3_owes_no_selector_evidence_for_a_scoped_run():
    assert "A run scoped by the repo's own rule (above) is not the narrowed command" in flat(step3())


def test_slice_one_suite_run_defers_to_the_repos_scope():
    text = slice_paragraph()
    start = text.index("as its one suite run, or the scope the repo's seam section names")
    assert "§ Review step 3" in text[start:start + 200]
