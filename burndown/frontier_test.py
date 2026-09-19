#!/usr/bin/env python3
"""Tests for the frontier reader (#890). Seam: `frontier(repo, label)` with
its two fetchers injected — a list of GitHub issue objects in, three buckets
(`unblocked`, `blocked`, `unresolved`) out. No network: every case is a
ticket fixture, which is the point of the seam.
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
    assert got == {"unblocked": [], "blocked": [], "unresolved": []}, got


def test_an_in_progress_ticket_is_off_the_frontier():
    got = read([issue(1, labels=("ready-for-agent", "in-progress"),
                      body="## Blocked by\n\nNone.\n")])
    assert got == {"unblocked": [], "blocked": [], "unresolved": []}, got


def test_a_pull_request_is_not_a_ticket():
    # The REST issues endpoint returns PRs too; they are not frontier work.
    got = read([issue(1, pull_request=True, body="## Blocked by\n\nNone.\n")])
    assert got == {"unblocked": [], "blocked": [], "unresolved": []}, got


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


def test_the_section_wins_over_an_inline_line():
    body = "Blocked by: #7\n\n## Blocked by\n\nNone.\n"
    got = read([issue(1, body=body)], states={7: "open"})
    assert numbers(got["unblocked"]) == [1], got


def test_prose_mentioning_a_blocker_mid_sentence_is_not_a_declaration():
    got = read([issue(1, body="This one is blocked by #7, we think.\n")],
               states={7: "open"})
    assert numbers(got["unresolved"]) == [1], got


def test_an_empty_inline_line_is_unresolved():
    got = read([issue(1, body="**Blocked by:**\n\nmore prose\n")])
    assert numbers(got["unresolved"]) == [1], got


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
