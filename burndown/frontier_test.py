#!/usr/bin/env python3
"""Tests for the frontier reader (#890). Seam: `frontier(repo, label)` with
its two fetchers injected — a list of GitHub issue objects in, four buckets
(`unblocked`, `blocked`, `unresolved`, `spec`) out. No network: every case is
a ticket fixture, which is the point of the seam.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frontier as F  # noqa: E402

FRONTIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontier.py")


def issue(number, *, title=None, body="", assignees=(), labels=("ready-for-agent",),
          blocked_by=None, total_blocked_by=None, pull_request=False):
    """One GitHub REST issue object, trimmed to the fields the reader reads.

    `blocked_by` / `total_blocked_by` are the native dependency counts;
    leaving both out is a ticket the tracker holds no dependency data for,
    which is what every pre-dependencies repo looks like.
    """
    out = {
        "number": number,
        "title": title or f"ticket {number}",
        "state": "open",
        "body": body,
        "assignees": [{"login": a} for a in assignees],
        "labels": [{"name": name} for name in labels],
    }
    if blocked_by is not None or total_blocked_by is not None:
        out["issue_dependencies_summary"] = {
            "blocked_by": blocked_by or 0,
            "total_blocked_by": total_blocked_by if total_blocked_by is not None
            else (blocked_by or 0),
        }
    if pull_request:
        out["pull_request"] = {"url": "https://example/pr"}
    return out


def read(issues, states=None):
    """`frontier(repo, label)` over a fixture list, with blocker states from a
    dict instead of the tracker. A number missing from `states` is a blocker
    whose state could not be read."""
    states = states or {}
    return F.frontier(
        "owner/repo", "ready-for-agent",
        fetch=lambda repo, label: issues,
        state_of=lambda repo, number: states.get(number),
    )


def numbers(bucket):
    return [entry["number"] for entry in bucket]


# Every bucket empty: what a ticket that is off the frontier altogether
# leaves behind. Spelled out rather than derived, so a bucket added without
# a thought about the off-the-frontier cases fails here.
EMPTY = {"unblocked": [], "blocked": [], "unresolved": [], "spec": []}


def unresolved_count(issues, dropped, states=None):
    """The size of the `unresolved` bucket over a fixture queue, read with
    `dropped` as the non-dispatchable label set.

    The harness behind the acceptance criterion "the unresolved count drops
    by exactly the number of tickets a label takes off the frontier": read
    the queue twice, once with the label set and once without, and the
    difference is the claim. It is parameterised on the label set so the
    claim is about any such label, not about one measured number on one
    repo on one afternoon."""
    original = F.NON_DISPATCHABLE_LABELS
    F.NON_DISPATCHABLE_LABELS = frozenset(dropped)
    try:
        return len(read(issues, states)["unresolved"])
    finally:
        F.NON_DISPATCHABLE_LABELS = original


# --- Native dependencies: the canonical path -------------------------------

def test_native_open_blocker_reads_as_blocked():
    got = read([issue(1, blocked_by=1, total_blocked_by=2)])
    assert numbers(got["blocked"]) == [1], got
    assert numbers(got["unblocked"]) == [], got
    assert numbers(got["unresolved"]) == [], got


def test_native_dependencies_all_closed_read_as_unblocked():
    # blocked_by counts open blockers only, so 0-of-2 is the live gate open.
    got = read([issue(1, blocked_by=0, total_blocked_by=2)])
    assert numbers(got["unblocked"]) == [1], got


def test_native_dependencies_beat_a_stale_blocked_by_section():
    # The section is prose someone typed; the tracker's edges are live.
    body = "## Blocked by\n\n- #7\n"
    got = read([issue(1, body=body, blocked_by=0, total_blocked_by=1)],
               states={7: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_no_native_edges_declared_falls_through_to_the_section():
    # total_blocked_by 0 is "this tracker holds no edges for this ticket",
    # not "this ticket is unblocked" — #781's repo looks exactly like this.
    got = read([issue(1, blocked_by=0, total_blocked_by=0)])
    assert numbers(got["unresolved"]) == [1], got


# --- The `## Blocked by` fallback grammar ----------------------------------

def test_section_naming_an_open_ticket_reads_as_blocked():
    # A blocked entry names the blockers still open, the way the native
    # `blocked_by` count does — the closed one no longer gates anything.
    got = read([issue(1, body="## Blocked by\n\n- #7\n- #8\n")],
               states={7: "closed", 8: "open"})
    assert numbers(got["blocked"]) == [1], got
    assert got["blocked"][0]["blockers"] == [8], got


def test_section_naming_only_closed_tickets_reads_as_unblocked():
    got = read([issue(1, body="## Blocked by\n\n- #7\n- #8\n")],
               states={7: "closed", 8: "closed"})
    assert numbers(got["unblocked"]) == [1], got


def test_section_stating_none_reads_as_unblocked():
    got = read([issue(1, body="## Blocked by\n\nNone — can start immediately.\n")])
    assert numbers(got["unblocked"]) == [1], got


def test_section_ends_at_the_next_heading():
    body = ("## Blocked by\n\nNone — can start immediately.\n\n"
            "## Seams under test\n\n- the frontier, blocked by #7\n")
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_heading_match_ignores_case_and_level():
    got = read([issue(1, body="# BLOCKED BY\n\n- #7\n")], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got


def test_a_reference_to_another_repo_is_not_a_bare_reference():
    # `owner/repo#7` is outside the grammar: the reader must not read its
    # tail as a local `#7`, and prose it cannot read is unresolved.
    got = read([issue(1, body="## Blocked by\n\n- caneff/other#7\n")],
               states={7: "closed"})
    assert numbers(got["unresolved"]) == [1], got


def test_a_blocker_whose_state_cannot_be_read_is_unresolved():
    got = read([issue(1, body="## Blocked by\n\n- #7\n")], states={})
    assert numbers(got["unresolved"]) == [1], got


# --- Silence is its own answer ---------------------------------------------

def test_a_ticket_with_no_section_at_all_is_unresolved():
    got = read([issue(1, body="## TL;DR\n\nSomething.\n")])
    assert numbers(got["unresolved"]) == [1], got
    assert numbers(got["unblocked"]) == [], got
    assert numbers(got["blocked"]) == [], got


def test_an_empty_section_is_unresolved():
    got = read([issue(1, body="## Blocked by\n\n## Seams under test\n\n- a seam\n")])
    assert numbers(got["unresolved"]) == [1], got


def test_a_section_of_unreadable_prose_is_unresolved():
    got = read([issue(1, body="## Blocked by\n\nthe database work, probably\n")])
    assert numbers(got["unresolved"]) == [1], got


def test_every_unresolved_entry_says_why():
    got = read([issue(1, body="nothing here"), issue(2, body="## Blocked by\n\n")])
    assert all(entry["why"] for entry in got["unresolved"]), got


# --- Claimed tickets are off the frontier ----------------------------------

def test_an_assigned_ticket_is_off_the_frontier():
    got = read([issue(1, assignees=("caneff",),
                      body="## Blocked by\n\nNone.\n")])
    assert got == EMPTY, got


def test_an_in_progress_ticket_is_off_the_frontier():
    got = read([issue(1, labels=("ready-for-agent", "in-progress"),
                      body="## Blocked by\n\nNone.\n")])
    assert got == EMPTY, got


def test_a_pull_request_is_not_a_ticket():
    # The REST issues endpoint returns PRs too; they are not frontier work.
    got = read([issue(1, pull_request=True, body="## Blocked by\n\nNone.\n")])
    assert got == EMPTY, got


# --- A spec parent is its own answer ---------------------------------------

def test_a_spec_parent_lands_in_its_own_bucket():
    # A spec parent is dispatchable work in a different mode, so it is not a
    # drop; and it needs no human to determine anything, so it is not
    # `unresolved`. Both available answers would be a lie about what it is.
    got = read([issue(1, labels=("ready-for-agent", "spec"),
                      body="No declaration at all.\n")])
    assert numbers(got["spec"]) == [1], got
    assert numbers(got["unblocked"]) == [], got
    assert numbers(got["blocked"]) == [], got
    assert numbers(got["unresolved"]) == [], got


def test_a_spec_entry_names_the_route_that_dispatches_it():
    # The point of the bucket: a controller reading the frontier can act on
    # the entry without opening another document. An entry that says "this
    # is a spec" and nothing else has only moved the problem.
    got = read([issue(885, labels=("ready-for-agent", "spec"),
                      body="No declaration at all.\n")])
    why = got["spec"][0]["why"]
    assert "implement-dispatch --spec 885 --slots" in why, why


def test_a_spec_parent_with_a_native_open_blocker_is_blocked():
    # `blocked` outranks `spec` on one entry: the frontier checks
    # prerequisites before it offers a route. The entry is true either way,
    # but `spec` carries a dispatch verb and a controller copies lines like
    # that — onto a whole nested run over blocked work.
    got = read([issue(1, labels=("ready-for-agent", "spec"), blocked_by=1)])
    assert numbers(got["blocked"]) == [1], got
    assert numbers(got["spec"]) == [], got


def test_a_spec_parent_whose_body_names_an_open_blocker_is_blocked():
    got = read([issue(1, labels=("ready-for-agent", "spec"),
                      body="## Blocked by\n\n- #7\n")], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got
    assert numbers(got["spec"]) == [], got


def test_a_spec_parent_whose_blockers_are_all_closed_is_dispatchable():
    # Prerequisites checked and met, so the route is the honest answer.
    got = read([issue(1, labels=("ready-for-agent", "spec"),
                      body="## Blocked by\n\n- #7\n")], states={7: "closed"})
    assert numbers(got["spec"]) == [1], got
    assert numbers(got["unblocked"]) == [], got


def test_a_spec_parent_whose_blockers_cannot_be_read_is_unresolved():
    # The ticket declared prerequisites this reader could not resolve, so
    # whether one is open is unknown — and an unknown prerequisite is not a
    # met one. Silence is the case that goes to `spec`; a declaration that
    # cannot be read is not silence.
    got = read([issue(1, labels=("ready-for-agent", "spec"),
                      body="## Blocked by\n\n- #7\n")], states={})
    assert numbers(got["unresolved"]) == [1], got
    assert numbers(got["spec"]) == [], got


def test_a_claimed_spec_parent_is_off_the_frontier_like_any_other():
    # A claim outranks the bucket: someone already has it, so there is no
    # route left to offer a controller.
    got = read([issue(1, labels=("ready-for-agent", "spec", "in-progress"),
                      body="No declaration at all.\n")])
    assert got == EMPTY, got


def test_a_spec_parent_moves_out_of_unresolved_rather_than_vanishing():
    # AC3's measurement: the `unresolved` count drops by exactly the number
    # of spec parents, because each one lands in `spec` instead. A drop that
    # left the queue smaller by one would pass a count check and still hide
    # the work, so the destination is asserted beside the count.
    # The spec branch reads the label off the issue, so no swap is involved
    # here and this is the shipped behaviour end to end.
    queue = [
        issue(1, labels=("ready-for-agent", "spec"),
              body="No declaration at all.\n"),
        issue(2, body="No declaration at all.\n"),
        issue(3, body="## Blocked by\n\nNone.\n"),
    ]
    got = read(queue)
    assert numbers(got["unresolved"]) == [2], got
    assert numbers(got["spec"]) == [1], got
    assert numbers(got["unblocked"]) == [3], got


def test_the_rendered_report_names_the_spec_route():
    # The reader's printed form is what a controller actually reads.
    line = F.render(read([issue(885, title="Spec: the lane",
                                labels=("ready-for-agent", "spec"),
                                body="No declaration at all.\n")]))
    assert line.startswith("spec        885 Spec: the lane  ("), line
    assert "implement-dispatch --spec 885 --slots <k>" in line, line


# --- Non-dispatchable tickets are off the frontier -------------------------

def test_a_needs_info_ticket_is_off_the_frontier():
    # `implement-dispatch` refuses a needs-info ticket outright: it waits on
    # grilling, not on another ticket. It is off the frontier by its own
    # nature, the way a claimed ticket is — not by a blocking relationship.
    got = read([issue(1, labels=("ready-for-agent", "needs-info"),
                      body="## Blocked by\n\nNone.\n")])
    assert got == EMPTY, got


def test_a_needs_info_ticket_with_no_blocked_by_is_dropped_not_unresolved():
    # The drop happens before any bucket is decided, so a silent body never
    # reaches the grammar. `unresolved` asks a human to determine this
    # ticket's blocking state; that is not the question a needs-info ticket
    # is waiting on, and padding the bucket with it trains a controller to
    # skim the one bucket that exists to be read.
    got = read([issue(1, labels=("ready-for-agent", "needs-info"),
                      body="Some body with no declaration at all.\n")])
    assert got == EMPTY, got


def test_dropping_a_label_lowers_unresolved_by_the_tickets_it_takes():
    # The measurement AC3 makes, as a fixture rather than a reading of one
    # repo: the queue the ticket names under Seams under test — two silent
    # tickets carrying the label, a claimed one, a well-formed child, and a
    # silent one that carries nothing.
    queue = [
        issue(1, labels=("ready-for-agent", "needs-info"),
              body="No declaration at all.\n"),
        issue(2, labels=("ready-for-agent", "needs-info"),
              body="No declaration at all.\n"),
        issue(3, labels=("ready-for-agent", "in-progress"),
              body="No declaration at all.\n"),
        issue(4, body="## Blocked by\n\n- #7\n"),
        issue(5, body="No declaration at all.\n"),
    ]
    states = {7: "open"}
    # #3 is claimed and #4 is blocked, so neither is ever unresolved.
    assert unresolved_count(queue, dropped=(), states=states) == 3, queue
    assert unresolved_count(queue, dropped=("needs-info",), states=states) == 1, queue
    # Bound to what ships, not only to the mechanism: reading with no swap
    # at all has to agree with naming the label by hand. Without this line
    # the test passes with `NON_DISPATCHABLE_LABELS` empty, which is the
    # one thing the measurement is supposed to be about.
    assert len(read(queue, states)["unresolved"]) == 1, F.NON_DISPATCHABLE_LABELS


def test_a_ticket_without_a_non_dispatchable_label_is_still_classified():
    # The filter takes only what it names: an ordinary ticket beside a
    # dropped one is unaffected.
    got = read([issue(1, labels=("ready-for-agent", "needs-info"),
                      body="## Blocked by\n\nNone.\n"),
                issue(2, body="## Blocked by\n\nNone.\n")])
    assert numbers(got["unblocked"]) == [2], got


# --- Shape -----------------------------------------------------------------

def test_buckets_are_ordered_by_number():
    issues = [issue(9, body="## Blocked by\n\nNone.\n"),
              issue(3, body="## Blocked by\n\nNone.\n")]
    got = read(issues)
    assert numbers(got["unblocked"]) == [3, 9], got


def test_each_blocker_state_is_read_once_per_number():
    calls = []

    def state_of(repo, number):
        calls.append(number)
        return "closed"

    issues = [issue(1, body="## Blocked by\n\n- #7\n"),
              issue(2, body="## Blocked by\n\n- #7\n")]
    F.frontier("owner/repo", "ready-for-agent",
               fetch=lambda repo, label: issues, state_of=state_of)
    assert calls == [7], calls


# --- The printed report ----------------------------------------------------

def test_the_report_names_a_blocked_ticket_s_open_blockers():
    got = read([issue(1, body="## Blocked by\n\n- #7\n")], states={7: "open"})
    assert F.render(got) == "blocked     1 ticket 1  (blocked by #7)", F.render(got)


def test_the_report_says_why_a_ticket_is_unresolved():
    got = read([issue(1, body="no section here")])
    line = F.render(got)
    assert line.startswith("unresolved  1 ticket 1  (no native dependencies "
                           "and no `Blocked by` of any form)"), line


def test_the_cli_refuses_a_wrong_argument_count():
    r = subprocess.run([sys.executable, FRONTIER, "owner/repo"],
                       capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "usage: frontier.py <owner/repo> <label>" in r.stderr, r.stderr


# --- The `gh` adapters -----------------------------------------------------

def test_a_label_with_odd_characters_is_encoded_into_the_url():
    # `#` in a raw URL is a fragment marker: gh drops it and answers a
    # broader queue with exit 0, which is the wrong answer reported as a
    # good one. A space hangs the request outright.
    calls = []
    got = F.fetch_issues("owner/repo", "needs info#1",
                         run=lambda args: calls.append(args) or [])
    assert got == [], got
    assert calls[0][-1].endswith("labels=needs%20info%231"), calls


def test_a_gh_call_that_answers_nothing_is_an_empty_queue():
    # A zero-exit `gh` with empty stdout parsed to None, and the frontier
    # then died on `TypeError: 'NoneType' object is not iterable`.
    assert F.fetch_issues("owner/repo", "l", run=lambda args: None) == []


def test_a_missing_gh_leaves_a_blocker_state_unread():
    def explode(args):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    assert F.fetch_state("owner/repo", 7, run=explode) is None


def test_the_cli_reports_a_failed_gh_call_on_one_line():
    r = subprocess.run([sys.executable, FRONTIER, "owner/repo", "l"],
                       capture_output=True, text=True,
                       env={**os.environ, "PATH": "/nonexistent"})
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stderr.count("\n") == 1, r.stderr
    assert "frontier.py: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr


# --- The two inline forms the tree also writes -----------------------------

def test_an_inline_blocked_by_line_names_blockers():
    # `docs/agents/issue-tracker.md`: a `Blocked by: #<n>, #<n>` line at the
    # top of the body, which is what /wayfinder children carry.
    body = "Part of #500\n\nBlocked by: #7, #8\n\nSome prose.\n"
    got = read([issue(1, body=body)], states={7: "closed", 8: "open"})
    assert numbers(got["blocked"]) == [1], got
    assert got["blocked"][0]["blockers"] == [8], got


def test_a_bold_inline_blocked_by_line_is_the_same_form():
    # `to-tickets`'s local ticket template writes `**Blocked by:** ...`.
    body = "**Blocked by:** None — can start immediately.\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unblocked"]) == [1], got


def test_a_closing_bold_marker_is_not_part_of_the_answer():
    # `**Blocked by**: None` puts the colon outside the markers; the answer
    # is what follows them, not `*: None`.
    got = read([issue(1, body="**Blocked by**: None — can start immediately.\n")])
    assert numbers(got["unblocked"]) == [1], got


def test_an_inline_line_reaches_only_to_its_end():
    body = "Blocked by: None — can start immediately.\n\nRelated: #7\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_an_inline_line_beside_a_section_is_two_declarations():
    body = "Blocked by: #7\n\n## Blocked by\n\nNone.\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["unresolved"]) == [1], got
    assert "more than once" in got["unresolved"][0]["why"], got


def test_prose_mentioning_a_blocker_mid_sentence_is_not_a_declaration():
    got = read([issue(1, body="This one is blocked by #7, we think.\n")],
               states={7: "open"})
    assert numbers(got["unresolved"]) == [1], got


def test_an_empty_inline_line_is_unresolved():
    got = read([issue(1, body="**Blocked by:**\n\nmore prose\n")])
    assert numbers(got["unresolved"]) == [1], got


# --- A quoted template is not a declaration -------------------------------

FENCED_TEMPLATE = """The ticket template we emit:

```
## Blocked by

None — can start immediately.
```

## TL;DR

Ship the thing.
"""


def test_a_fenced_section_is_a_quoted_example_not_a_declaration():
    # to-tickets/SKILL.md carries exactly this fenced template, and any
    # ticket quoting the grammar carries one too. Reading it as a real
    # declaration is the false-ready dispatch this whole reader exists to
    # stop.
    got = read([issue(1, body=FENCED_TEMPLATE)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_fenced_inline_example_is_not_a_declaration():
    # In the preamble, where a real inline declaration would count, and
    # tilde-fenced rather than backtick-fenced.
    body = "~~~\nBlocked by: None\n~~~\n\n## TL;DR\n\nSomething.\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_real_section_after_a_fenced_example_is_still_read():
    # The fence has to close: swallow the rest of the body and this ticket's
    # own declaration disappears into the quoted example.
    body = "```\n## Blocked by\n\nNone.\n```\n\n## Blocked by\n\n- #7\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got


def test_an_inline_line_counts_only_in_the_preamble():
    # The grammar puts the inline form at the top of the body. Below a
    # heading it is prose about blockers, not the ticket's declaration.
    body = "## TL;DR\n\nSomething.\n\nBlocked by: None — can start immediately.\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_preamble_inline_line_still_declares():
    body = "Part of #500\n\nBlocked by: None\n\n## TL;DR\n\nSomething.\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unblocked"]) == [1], got


# --- A queue past one page -------------------------------------------------

def test_every_page_of_a_paginated_queue_comes_back():
    pages = [[issue(1), issue(2)], [issue(3)]]
    got = F.fetch_issues("owner/repo", "l", run=lambda args: pages)
    assert [i["number"] for i in got] == [1, 2, 3], got


def test_the_paginated_fetch_asks_gh_to_slurp_the_pages():
    calls = []
    F.fetch_issues("owner/repo", "l", run=lambda args: calls.append(args) or [])
    assert "--slurp" in calls[0], calls


def test_an_answer_that_is_not_pages_of_issues_is_an_error():
    for answer in ({"message": "Not Found"}, [{"number": 1}]):
        try:
            F.fetch_issues("owner/repo", "l", run=lambda args: answer)
        except F.FrontierError as exc:
            assert "pages" in str(exc), exc
        else:
            raise AssertionError(f"{answer!r} must not pass for a queue")


# --- A long fence protects a fence -----------------------------------------

# Four backticks are exactly what you reach for to quote content that itself
# contains a triple-backtick fence — which is what a ticket quoting this
# repo's own grammar doc does. One inner fence line, deliberately an odd
# count: with an even count the heading lands back inside the fence and a
# broken reader looks correct.
LONG_FENCE = "\n".join([
    "````",
    "quoted template, showing a fence:",
    "```",
    "## Blocked by",
    "",
    "None — can start immediately",
    "````",
    "",
])

LONG_TILDE_FENCE = "\n".join([
    "~~~~",
    "quoted template, showing a fence:",
    "~~~",
    "## Blocked by",
    "",
    "None — can start immediately",
    "~~~~",
    "",
])


def test_a_shorter_fence_inside_a_longer_one_does_not_close_it():
    got = read([issue(1, body=LONG_FENCE)])
    assert numbers(got["unresolved"]) == [1], got


def test_the_fence_length_rule_is_not_backtick_specific():
    got = read([issue(1, body=LONG_TILDE_FENCE)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_fence_closes_only_on_its_own_character():
    # A `~~~` line inside a backtick fence is content. If it were read as a
    # closer, everything after it — the whole quoted template — would come
    # back as this ticket's own declaration.
    body = "```\nquoted template:\n~~~\n\n## Blocked by\n\nNone.\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_closing_fence_may_not_carry_an_info_string():
    # CommonMark: an opener may be ```python, a closer may not. Reading one
    # as a closer hands the rest of the quotation back as live document.
    body = "```\nquoted example:\n```python\n\n## Blocked by\n\nNone.\n```\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unresolved"]) == [1], got


def test_a_longer_run_closes_a_shorter_fence():
    # CommonMark: the closer must be at least as long as the opener, so a
    # longer one still closes. The declaration after it is this ticket's.
    body = "```\nquoted\n`````\n\n## Blocked by\n\n- #7\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got


# --- Two visible declarations are ambiguous (#922) -----------------------

QUOTED_THEN_REAL = """Evidence, quoting the other ticket:

## Blocked by

- #906

And here is the real declaration appended by the skill:

## Blocked by

None — can start immediately.
"""


def test_two_visible_sections_are_unresolved_not_first_wins():
    got = read([issue(1, body=QUOTED_THEN_REAL)], states={906: "open"})
    assert numbers(got["unresolved"]) == [1], got
    assert got["blocked"] == [] and got["unblocked"] == [], got


def test_the_ambiguity_reason_is_not_the_silence_reason():
    got = read([issue(1, body=QUOTED_THEN_REAL)])
    why = got["unresolved"][0]["why"]
    assert "more than once" in why, why
    assert "states nothing" not in why, why


def test_a_fenced_quotation_beside_one_declaration_is_not_ambiguous():
    body = "```\n## Blocked by\n\n- #906\n```\n\n## Blocked by\n\nNone.\n"
    got = read([issue(1, body=body)], states={906: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_an_indented_quotation_beside_one_declaration_is_not_ambiguous():
    # Indented four spaces or more is an indented code block, not a heading.
    body = "    ## Blocked by\n\n    - #906\n\n## Blocked by\n\nNone.\n"
    got = read([issue(1, body=body)], states={906: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_two_inline_lines_in_the_preamble_are_ambiguous():
    body = "Blocked by: #7\nBlocked by: None\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["unresolved"]) == [1], got
    assert "more than once" in got["unresolved"][0]["why"], got


def test_one_declaration_is_unchanged():
    got = read([issue(1, body="## Blocked by\n\n- #7\n")], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got


def test_an_ambiguous_spec_parent_stays_unresolved():
    got = read([issue(1, body=QUOTED_THEN_REAL, labels=("ready-for-agent", "spec"))])
    assert numbers(got["unresolved"]) == [1], got
    assert "more than once" in got["unresolved"][0]["why"], got


def test_an_indented_inline_line_is_a_quotation_not_a_declaration():
    # Four spaces or a tab is an indented code block. Beside a real inline
    # line it must not make the body ambiguous.
    for quoted in ("    Blocked by: #7", "\tBlocked by: #7"):
        body = quoted + "\nBlocked by: None\n"
        got = read([issue(1, body=body)], states={7: "open"})
        assert numbers(got["unblocked"]) == [1], (quoted, got)


def test_an_indented_section_after_a_real_one_adds_nothing_to_its_answer():
    # Codex on #996: the indent bound kept the quoted heading from counting as
    # a second declaration, but its lines still joined the real section's
    # payload and its `#906` blocked the ticket.
    body = "## Blocked by\n\nNone\n\n    ## Blocked by\n\n    - #906\n"
    got = read([issue(1, body=body)], states={906: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_a_quoted_line_after_a_real_section_adds_nothing_to_its_answer():
    body = "## Blocked by\n\nNone\n\n> Blocked by: #906\n> - #906\n"
    got = read([issue(1, body=body)], states={906: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_a_tab_indented_line_after_a_real_section_adds_nothing_to_its_answer():
    body = "## Blocked by\n\nNone\n\n\t- #906\n"
    got = read([issue(1, body=body)], states={906: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_an_indented_fence_marker_in_a_quotation_does_not_swallow_the_real_declaration():
    # #999: CommonMark reads a four-space-indented ``` as indented code, not
    # a fence opener. A reader that opens a fence on it anyway, with no
    # closer in the quoted block, discards every later line — including the
    # real, unindented declaration.
    body = "Quoting another ticket:\n\n    ```\n    some quoted code\n\n## Blocked by\n\nNone\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unblocked"]) == [1], got


def test_a_tab_indented_fence_marker_in_a_quotation_does_not_swallow_the_real_declaration():
    # Same bug as above, tab rather than four spaces — CommonMark treats a
    # tab the same way (#999, round-1 review: the four-space fixture alone
    # left this half of the bound unwitnessed).
    body = "Quoting another ticket:\n\n\t```\n\tsome quoted code\n\n## Blocked by\n\nNone\n"
    got = read([issue(1, body=body)])
    assert numbers(got["unblocked"]) == [1], got


def test_an_indented_closer_does_not_end_an_unindented_fence_early():
    # The closer half of the same bound (#999, round-1 review): CommonMark
    # bounds a closing fence marker the same way as an opener — a
    # 4-space-indented ``` inside a real, unindented fence is quoted content,
    # not the closer, so the fence stays open through it and the quoted
    # `## Blocked by` inside stays quoted.
    body = ("```\nquoted example:\n    ```\n\n## Blocked by\n\nNone.\n```\n\n"
            "## Blocked by\n\n- #7\n")
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["blocked"]) == [1], got


def test_a_folded_per_pr_body_keeps_one_blocked_by_declaration():
    """#1033 Codex gate finding 1: the run sweep already declares its own
    `## Blocked by`; appending a per-PR sweep's whole body would add a
    second one and read AMBIGUOUS, dropping the folded run sweep off the
    frontier for good. Mirrors the split
    `burndown/SKILL.md` § The sweep's fold uses — `gh issue view --jq
    '.body | split("\n## Blocked by")[0]'` — to strip the per-PR body's
    own section before it is appended."""
    run_sweep_body = ("## a.py\n\n- bullet\n\n"
                       "## Blocked by\n\nNone — can start immediately.\n")
    per_pr_body = ("## b.py\n\n- another bullet\n\n"
                    "## Blocked by\n\nNone — can start immediately.\n")
    per_pr_files_only = per_pr_body.split("\n## Blocked by")[0]
    folded = run_sweep_body + per_pr_files_only
    assert F.blocked_by_section(folded) == F.blocked_by_section(run_sweep_body), folded
    assert F.blocked_by_section(folded) is not None, folded


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
