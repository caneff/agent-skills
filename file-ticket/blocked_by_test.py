#!/usr/bin/env python3
"""Runs `/file-ticket`'s own issue template through the frontier reader (#911).

The seam is what the skill writes — the issue body — so this test takes the
body template out of `file-ticket/SKILL.md` and classifies it with
`burndown/frontier.py`, the reader that consumes it. A ticket this skill
files must land in `unblocked` or `blocked`, never `unresolved`: on
`agent-skills` seven of the eight unresolved `ready-for-agent` tickets on
2026-09-20 were filed ad hoc during builds, each costing a controller a
decision by hand.

`file-ticket/blocked-by-wording.test.sh` asserts the prose that tells the
filer to emit it; this file asserts the template actually parses.
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


def classify(body, states=None):
    """Which bucket the frontier reader puts this filed ticket in. No native
    dependency data: the fallback grammar is what the body has to satisfy.

    `"no bucket"` rather than a traceback if the fixture ever stops being a
    ticket the reader ranks at all — a failed check is one line here, the
    way `frontier.py` gives a failed read one line."""
    states = states or {}
    issue = {"number": 42, "title": "a filed finding", "body": body,
             "assignees": [], "labels": [{"name": "ready-for-agent"}]}
    buckets = F.classify([issue], lambda n: states.get(n))
    named = [name for name, entries in buckets.items() if entries]
    return named[0] if named else "no bucket"


def case(name, got, want):
    if got == want:
        return 0
    print(f"FAIL {name}: classified {got}, wanted {want}", file=sys.stderr)
    return 1


def main():
    fail = 0
    # The template as it ships — no blockers — is a statement, not silence.
    fail += case("template as shipped", classify(filed(BODY)), "unblocked")

    # The blocker form the skill documents: the `None` line replaced by one
    # bare reference per blocking issue. Its absence is a scored failure
    # rather than an assert, so the cases below it still run and report.
    blocked = filed(BODY).replace("- None — can start immediately.", "- #890")
    fail += case("the template states `None` the documented way",
                 "#890" in blocked, True)
    fail += case("one open blocker", classify(blocked, {890: "open"}), "blocked")
    fail += case("blocker since closed", classify(blocked, {890: "closed"}), "unblocked")

    # The native edge is a second command, so it may never be made — an old
    # `gh`, a tracker with no dependency support. The filed body carries the
    # whole answer on its own: every case here classifies a ticket with no
    # `issue_dependencies_summary` at all, and this one says so by name.
    fail += case("native edge rejected, body alone",
                 classify(blocked, {890: "open"}), "blocked")

    # Only the section answers. The same body without it carries `#906` in
    # its prose and still reads as silence — which is why the skill cannot
    # leave the section to the filer's judgement.
    fail += case("prose reference, no section", classify(BODY, {906: "open"}),
                 "unresolved")

    # A quoted scrap of another ticket — `> ` per line — cannot speak for
    # this one, so the appended section still answers.
    quoted = filed(BODY + "\n\nThe ticket it came from says:\n\n"
                   "> ## Blocked by\n>\n> - #906")
    fail += case("blockquoted evidence heading", classify(quoted, {906: "open"}),
                 "unblocked")

    # The same scrap pasted bare is what the skill's quoting rule exists to
    # stop: the reader takes the first visible declaration, so an evidence
    # heading beats the section below it and the ticket answers with a
    # number it never claimed. Asserted as "not the section's own verdict"
    # rather than a bucket, since #922 changes which wrong answer it is.
    bare = filed(BODY + "\n\nThe ticket it came from says:\n\n"
                 "## Blocked by\n\n- #906")
    fail += case("bare evidence heading overrides the section",
                 classify(bare, {906: "open"}) != "unblocked", True)

    # Evidence pasted as a fenced block is quoted material to the reader; a
    # closed fence leaves the section below it visible.
    fenced = filed(BODY + "\n\n```\n## Blocked by\n\n- #906\n```")
    fail += case("fenced evidence below the body", classify(fenced, {906: "open"}),
                 "unblocked")

    if fail:
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
