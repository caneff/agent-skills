---
name: burndown
description: "Burn down the ticket queue: loop /implement over every open ready-for-agent issue, frontier-first, until the queue is empty."
disable-model-invocation: true
---

# Burn down the ticket queue

Work the repo's `ready-for-agent` queue to empty, one ticket at a time.
Strictly sequential: each ticket lands on main before the next starts, so
later builds rebase onto earlier ones instead of colliding.

## The loop

1. List the queue: `gh issue list --label ready-for-agent --state open`.
   Empty → report and stop.
2. Pick from the **frontier**: a ticket whose blockers are all closed. Check
   each candidate's blocking edges (native blocking link, or the "Blocked by"
   section in the body); skip any with an open blocker. Among unblocked
   tickets, take the lowest number.
3. **Build.** Run the [`implement`](../implement/SKILL.md) skill on it —
   claim, delegate the build to a subagent — with one change to that skill's
   sequencing: seed the builder to stop after committing, report its branch,
   and wait. The driver owns review and land (next steps); everything else in
   `implement`, including its gates, applies unchanged.
4. **Review.** Spawn a fresh reviewer subagent (`opus`) for this ticket,
   seeded with only the issue reference and the branch — never the burn
   history. It runs `/code-review` against the issue spec and owns the
   verdict: **clean** or **can't get clean**. Findings pass through the
   driver to the builder verbatim; the builder fixes, the reviewer
   re-reviews. The driver carries mail and acts on the verdict — it judges
   nothing, and the builder never certifies its own work.
5. **Land.** On **clean**, tell the builder to land, per `implement`'s
   landing section. On **can't get clean**, park the ticket (below).
6. Append to the progress file at
   `~/.cache/burndown/<repo dir name>.progress` (never in the repo):
   `burning #<n>` when claiming in step 3, then `#<n> landed <sha>` or
   `#<n> parked: <why>` when the ticket settles, and `done` when the loop
   stops. The statusline renders this file live; the line grammar is a
   contract with `ccstatusline-table/helpers/burndown-segment.sh` — change
   the two only in lockstep.
7. Go to 1. Re-list every pass: a landing can unblock tickets, and a human
   may have added more.

## Driver context stays thin

The tracker and the progress file are the state, not this conversation:
re-derive the queue every pass, and keep one line per finished ticket in
context — build detail lives with the builder, review detail in the review
report. A burn survives summarization this way, and a fresh session can
resume a half-done queue from the tracker and progress file alone.

## When a ticket can't land

A build that hits a stop-and-ask gate or a non-mechanical conflict, with no
human answering: **park it** — comment the open question on the issue, swap
`in-progress` for `ready-for-human`, and move on to the next ticket. Two
parks in a row means the problem is systemic, not per-ticket: stop the burn
and report instead of parking the whole queue.

## Report

When the loop stops, tally: tickets landed (issue → commit), tickets parked
and why, tickets still open and what blocks them.
