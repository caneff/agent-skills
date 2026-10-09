"""Runs `/file-ticket`'s own issue template through the frontier reader (#911).

The seam is what the skill writes — the issue body — so this test takes the
body template out of `file-ticket/SKILL.md` and classifies it with
`burndown/frontier.py`, the reader that consumes it. A ticket this skill
files must land in `unblocked` or `blocked`, never `unresolved` (one carve-out: a
cross-repo blocker reads `unresolved` until its native edge exists, which
the last cases pin): on
`agent-skills` seven of the eight unresolved `ready-for-agent` tickets on
2026-09-20 were filed ad hoc during builds, each costing a controller a
decision by hand.

This file asserts the template actually parses.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "file-ticket" / "SKILL.md"

sys.path.insert(0, str(ROOT / "burndown"))
import frontier as F  # noqa: E402

# The `gh issue create` heredoc in § Create it: the body runs from the quoted
# `EOF` opener to the terminator on its own line.
TEMPLATE = re.compile(r"--body \"\$\(cat <<'EOF'\n(?P<body>.*?)\nEOF\n", re.DOTALL)

BODY = ("The label mapping and the tracker doc name different defaults, so a "
        "filer picks one by eye. `docs/agents/triage-labels.md`, grep "
        "`needs-triage`.\n\nFiled from a review of PR #906.")


def template():
    found = TEMPLATE.search(SKILL.read_text())
    assert found, "file-ticket/SKILL.md has no `gh issue create` body heredoc"
    return found.group("body")


def filed(body):
    """The body `/file-ticket` would create, with its `<body>` placeholder
    filled the way a real filing fills it."""
    return template().replace("<body>", body)


def classify(body, states=None, deps=None):
    """Which bucket the frontier reader puts this filed ticket in. No native
    dependency data: the fallback grammar is what the body has to satisfy.

    `"no bucket"` rather than a traceback if the fixture ever stops being a
    ticket the reader ranks at all — a failed check is one line here, the
    way `frontier.py` gives a failed read one line."""
    states = states or {}
    issue = {"number": 42, "title": "a filed finding", "body": body,
             "assignees": [], "labels": [{"name": "ready-for-agent"}]}
    if deps:
        issue["issue_dependencies_summary"] = deps
    buckets = F.classify([issue], lambda n: states.get(n), lambda ticket: None)
    named = [name for name, entries in buckets.items() if entries]
    return named[0] if named else "no bucket"


NONE_LINE = "- None — can start immediately."


def blocked_body():
    """The blocker form the skill documents: the `None` line replaced by one
    bare reference per blocking issue."""
    return filed(BODY).replace(NONE_LINE, "- #890")


def cross_repo_body():
    return filed(BODY).replace(NONE_LINE, "- caneff/sudokumaker#906")


def test_template_as_shipped_is_unblocked():
    # No blockers is a statement, not silence.
    assert classify(filed(BODY)) == "unblocked"


def test_template_states_none_the_documented_way():
    assert "#890" in blocked_body()


def test_one_open_blocker_blocks():
    assert classify(blocked_body(), {890: "open"}) == "blocked"


def test_blocker_since_closed_is_unblocked():
    assert classify(blocked_body(), {890: "closed"}) == "unblocked"


def test_prose_reference_without_the_section_is_unresolved():
    # Only the section answers. The same body without it carries `#906` in
    # its prose and still reads as silence, which is why the skill cannot
    # leave the section to the filer's judgement.
    assert classify(BODY, {906: "open"}) == "unresolved"


def test_blockquoted_evidence_heading_does_not_speak_for_the_ticket():
    # A quoted scrap of another ticket, `> ` per line, so the appended
    # section still answers.
    quoted = filed(BODY + "\n\nThe ticket it came from says:\n\n"
                   "> ## Blocked by\n>\n> - #906")
    assert classify(quoted, {906: "open"}) == "unblocked"


def test_bare_evidence_heading_overrides_the_section():
    # The same scrap pasted bare is what the skill's quoting rule exists to
    # stop: the reader takes the first visible declaration, so an evidence
    # heading beats the section below it. Asserted as "not the section's
    # own verdict" rather than a bucket, since #922 changes which wrong
    # answer it is.
    bare = filed(BODY + "\n\nThe ticket it came from says:\n\n"
                 "## Blocked by\n\n- #906")
    assert classify(bare, {906: "open"}) != "unblocked"


def test_fenced_evidence_below_the_body_is_quoted_material():
    fenced = filed(BODY + "\n\n```\n## Blocked by\n\n- #906\n```")
    assert classify(fenced, {906: "open"}) == "unblocked"


def test_cross_repo_blocker_without_a_native_edge_is_unresolved():
    # The skill writes the full `owner/repo#N` form, which the grammar
    # refuses on purpose: never gated on an unrelated local #N, never
    # unblocked.
    assert classify(cross_repo_body(), {906: "open"}) == "unresolved"


def test_cross_repo_blocker_with_a_native_edge_is_blocked():
    deps = {"total_blocked_by": 1, "blocked_by": 1}
    assert classify(cross_repo_body(), deps=deps) == "blocked"
