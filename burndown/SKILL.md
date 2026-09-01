---
name: burndown
description: "Burn down the ticket queue: loop /implement over every open ready-for-agent issue, frontier-first, until the queue is empty."
disable-model-invocation: true
---

# Burn down the ticket queue

Work the repo's `ready-for-agent` queue to empty. The tickets are a graph, not
a list: their blocking edges say which ones are independent, so the driver
builds the whole unblocked **frontier** at once and lands the results one at a
time.

**Arguments:** `/burndown [builders] [tickets]` — the maximum number of live
builders (default 3) and the maximum number of tickets this burn will settle
(default 15). `/burndown 1` builds strictly one ticket at a time. A burn stops
at the ticket cap even with the queue non-empty; run it again to continue,
since the tracker and the progress file hold all the state.

The ticket cap is sized for the explorer in step 3, not for the driver: one
`sonnet` agent reads each ticket's issue and the files it touches, then writes
the notes. At 15 tickets that fits a 200k window with room to think; past 20 it
skims, and skimmed notes read the same as good ones. Raise it when you have
watched a burn and the notes held up.

## The loop

1. List the queue: `gh issue list --label ready-for-agent --state open`.
   Empty, with nothing in flight → report and stop.
2. Take the **frontier**: every ticket whose blockers are all closed. Check
   each candidate's blocking edges (native blocking link, or the "Blocked by"
   section in the body); skip any with an open blocker. Take the lowest
   numbers first, up to the number of free builder slots. That set is this
   pass's **batch**.
3. **Explore once per burn — first pass only.** On the first pass, spawn one
   exploration subagent (`sonnet`) over **the tickets this burn can reach** —
   step 1's listing in dependency order, cut at the ticket cap — not just this
   pass's frontier. Blocked tickets are in scope: each one can land before the
   burn ends, so the explorer covers the whole burn in one read. The cap is
   what keeps that one read from going thin over a long queue.
   It reads the code and docs those tickets touch and writes its notes to
   `~/.cache/burndown/<repo dir name>.notes.md` — outside the repo, so every
   builder and every worktree can read it. Builders **wait** for it: a builder
   that starts early has already done the reading the explorer was meant to
   save. Notes are kept after the burn.

   Every later pass **skips this step** and points its builders at the same
   file. A refill batch is usually one ticket, and one explorer per ticket
   costs more than it saves. A builder that finds the notes thin for its
   ticket reads the code itself.

   One exception: if a later pass lists a ticket that was **not** in the pass-1
   queue — a human added it mid-burn — explore that ticket alone and append to
   the same notes file.
4. **Build.** Run the [`implement`](../implement/SKILL.md) skill on each ticket
   in the batch — claim, one workspace per ticket — with one change to that
   skill's sequencing: seed the builder to stop after committing, report its
   branch, and wait. The driver owns review and the PR (next steps);
   everything else in `implement`, including its gates, applies unchanged.

   **Seed by pointer.** A builder gets the issue reference, the notes path,
   and the branch base — never a summary of something it can read itself.
5. **Review.** Spawn a fresh reviewer subagent (`opus`) for each finished
   ticket, seeded with only the issue reference and the branch — never the
   burn history, and never the explorer's notes. A reviewer that re-reads the
   code independently is the point of having one. It runs `/code-review`
   against the issue spec and owns the verdict: **clean** or **can't get
   clean**. Findings pass through the driver to the builder verbatim; the
   builder fixes, the reviewer re-reviews. The driver carries mail and acts on
   the verdict — it judges nothing, and the builder never certifies its own
   work. Reviewers run concurrently and do not count against the builder cap.
6. **Land, one at a time**, in the order reviews come back clean. On
   **clean**, tell the builder to land, per `implement`'s landing section. On
   **can't get clean**, park the ticket (below).

   A builder still mid-build on a stale base needs no warning: the PR reports
   the conflict against the pushed default branch, so a real collision
   surfaces there and parks the ticket.

   Either way the settled ticket's builder is spent: **release it** —
   `TaskStop` with its name. A burndown builder waits for review, so it must
   be a named background agent, and a named agent parks idle forever unless
   the driver stops it. Stop each builder as its ticket settles; a queue of
   ten tickets must not leave ten idle agents behind.
7. Append to the progress file at
   `~/.cache/burndown/<repo dir name>.progress` (never in the repo):
   `burning #<n>` when claiming in step 4, then `#<n> landed <sha>` or
   `#<n> parked: <why>` when the ticket settles, and `done` when the loop
   stops. Several `burning` lines are open at once while a batch runs — that
   is how the file expresses parallelism. The statusline renders this file
   live; the line grammar is a contract with
   `ccstatusline-table/helpers/burndown-segment.sh` — change the two only in
   lockstep.
8. When a ticket settles, refill its slot: go to 1, skipping step 3. Re-list
   every pass — a landing can unblock tickets, and a human may have added
   more. At the ticket cap — landed plus parked — start no new builders, let
   the live ones settle, and stop.

## Driver context stays thin

The tracker and the progress file are the state, not this conversation:
re-derive the queue every pass, and keep one line per finished ticket in
context — build detail lives with the builder, review detail in the review
report. A burn survives summarization this way, and a fresh session can
resume a half-done queue from the tracker and progress file alone.

## When a ticket can't land

A build that hits a stop-and-ask gate or a non-mechanical conflict, with no
human answering: **park it** — comment the open question on the issue, swap
`in-progress` for `ready-for-human`, and move on to the next ticket. Two parks
with no landing between them means the problem is systemic, not per-ticket:
stop the burn and report instead of parking the whole queue. (Two parks in a
row is a coincidence when three builders run at once; two parks with nothing
getting through is not.)

## Report

When the loop stops, tally: tickets landed (issue → commit), tickets parked
and why, tickets still open and what blocks them. Say why the loop stopped —
queue empty, ticket cap, or two parks with no landing — and if the queue is
not empty, say to run `/burndown` again.
