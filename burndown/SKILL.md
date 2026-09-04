---
name: burndown
description: "Drain a mixed-origin ticket queue to empty as one supervised Orca run, frontier-first, one PR per ticket."
disable-model-invocation: true
---

You are the **coordinator**: a top-level Claude session in the queue's repo,
started against the `ready-for-agent` label. This file is policy. Every
command is an Orca verb: run `orca-ide skills get orchestration` and
`orca-ide skills get orca-cli` before the first one and follow that grammar,
which is version-matched to the binary.

A single spec's slices in one Orca workspace are
[`implement-spec`](../implement-spec/SKILL.md)'s job, not this skill's — use
that instead when every ticket traces to the same spec issue.

**Arguments:** `/burndown [builders] [tickets]` — the maximum number of live
worker tasks (default 3) and the maximum number of tickets this burn will
settle (default 15). `/burndown 1` builds strictly one ticket at a time. A
burn stops at the ticket cap even with the queue non-empty; run it again to
continue, since the tracker and the progress file hold all the state.

## Shape

Mirrors `implement-spec`: one Run, one Task per ticket, dependencies as
blocking edges, workers via Orca `claude`/`sonnet` (or `opus` if the ticket
names it), frontier = Orca's ready-task query. Unlike `implement-spec`, the
ticket set is not fixed up front — the queue is mixed-origin and re-listed
every pass, so a task is created for a ticket only once it enters the
frontier, and a landing or a human adding tickets can grow the queue mid-burn.

One **exploration** task, first pass only, covering every ticket this burn
can reach — step 1's listing in dependency order, cut at the ticket cap, not
just the first pass's frontier — that every ticket task depends on. The cap is
sized for this read: at 15 tickets it fits a 200k window with room to think;
past 20 it skims. Notes go to `~/.cache/burndown/<repo dir name>.notes.md`,
outside the repo so every worker can read them, and are kept after the burn.
A later pass that lists a ticket not in the pass-1 queue explores that ticket
alone and appends to the same file.

## The loop

1. List the queue: `gh issue list --label ready-for-agent --state open`.
   Empty, with nothing in flight → report and stop.
2. Take the **frontier** via Orca's ready-task query: every ticket whose
   blockers are all closed, lowest numbers first, up to the free worker
   slots. That set is this pass's batch.
3. First pass only: run exploration (above). Every later pass skips this and
   points its workers at the same notes file.
4. **Build.** Dispatch one Orca task per ticket in the batch, running the
   [`implement`](../implement/SKILL.md) skill's § Build by pointer — the
   issue reference, the notes path, and the branch base, never a summary.
   Seed the worker to stop after committing, report its branch, and wait; the
   coordinator owns review and the PR.
5. **Review.** Once a worker reports its branch, dispatch a review task
   seeded with only the issue reference and the branch — never the burn
   history or the explorer's notes — running the
   [`code-review`](../code-review/SKILL.md) skill by pointer, not by slash
   invocation. It owns the verdict: **clean** or **can't get clean**.
   Findings pass through the coordinator to the builder verbatim; the builder
   fixes, the reviewer re-reviews. Review tasks run concurrently and do not
   count against the builder cap.
6. **Land, one at a time**, in the order reviews come back clean, per
   `implement`'s [Finish](../implement/SKILL.md) section. On **can't get
   clean**, park the ticket
   (below). A worker still mid-build on a stale base needs no warning: the PR
   reports the conflict against the pushed default branch, so a real
   collision surfaces there and parks the ticket. Either way the settled
   ticket's task is done — an Orca task ends with its worker, so there is no
   separate release step.
7. Append to the progress file at
   `~/.cache/burndown/<repo dir name>.progress` (never in the repo) as the
   loop claims, settles, and finishes tickets. The statusline renders this
   file live; the line grammar is documented once, in
   [`flow/ccstatusline-table/helpers/burndown-segment.sh`](../flow/ccstatusline-table/helpers/burndown-segment.sh).
8. When a ticket settles, refill its slot: go to 1, skipping step 3. Re-list
   every pass — a landing can unblock tickets, and a human may have added
   more. At the ticket cap — landed plus parked — start no new tasks, let the
   live ones settle, and stop.

## Coordinator context stays thin

The tracker and the progress file are the state, not this conversation:
re-derive the queue every pass, and keep one line per finished ticket in
context — build detail lives with the worker, review detail in the review
report. A burn survives summarization this way, and a fresh session can
resume a half-done queue from the tracker and progress file alone.

## When a ticket can't land

A build that hits a stop-and-ask gate or a non-mechanical conflict, with no
human answering: **park it** — comment the open question on the issue, swap
`in-progress` for `ready-for-human`, and move on to the next ticket. Two parks
with no landing between them means the problem is systemic, not per-ticket:
stop the burn and report instead of parking the whole queue. (Two parks in a
row is a coincidence when three workers run at once; two parks with nothing
getting through is not.)

## Report

When the loop stops, tally: tickets landed (issue → commit), tickets parked
and why, tickets still open and what blocks them. Say why the loop stopped —
queue empty, ticket cap, or two parks with no landing — and if the queue is
not empty, say to run `/burndown` again.
