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
3. Run the [`implement`](../implement/SKILL.md) skill on it — claim, delegate
   the build to a subagent, land. Every gate in that skill applies unchanged.
4. Append one line (`#<n> landed <sha>`, or `#<n> parked: <why>`) to a
   progress file in scratch — never in the repo.
5. Go to 1. Re-list every pass: a landing can unblock tickets, and a human
   may have added more.

## When a ticket can't land

A build that hits a stop-and-ask gate or a non-mechanical conflict, with no
human answering: **park it** — comment the open question on the issue, swap
`in-progress` for `ready-for-human`, and move on to the next ticket. Two
parks in a row means the problem is systemic, not per-ticket: stop the burn
and report instead of parking the whole queue.

## Report

When the loop stops, tally: tickets landed (issue → commit), tickets parked
and why, tickets still open and what blocks them.
