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
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this skill's — use
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

One **exploration** pass, first pass only, covering every ticket this burn
can reach — step 1's listing in dependency order, cut at the ticket cap, not
just the first pass's frontier — that every ticket task depends on. The cap is
sized for this read: at 15 tickets it fits a 200k window with room to think;
past 20 it skims. Notes go to `~/.cache/burndown/<repo dir name>.notes.md`,
outside the repo so every worker can read them, and are kept after the burn.
A later pass that lists a ticket not in the pass-1 queue explores that ticket
alone and appends to the same file.

Exploration must report **collisions**: any file two tickets in the batch would
both touch. Resolve every collision before dispatching — narrow one ticket's
scope to what its own issue already permits, or serialise the pair — and say in
each builder's seed which files are its own. Two builders editing one file is a
merge conflict the coordinator caused.

Exploration is read-only and needs no worktree, terminal, or Orca task: run it
as an in-process `Explore` subagent (`Agent` tool, `model: sonnet`) and read
its result directly. **Only builders are Orca tasks** — they are the only
workers that write code and need their own worktree and branch. Everything
read-only, exploration and review both, is an in-process subagent.

## The loop

1. List the queue: `gh issue list --label ready-for-agent --state open`.
   Empty, with nothing in flight → report and stop.
2. Take the **frontier** via Orca's ready-task query: every ticket whose
   blockers are all closed, lowest numbers first, up to the free worker
   slots. That set is this pass's batch.
3. First pass only: run exploration (above) as a subagent and wait for its
   result before dispatching builders. Every later pass skips this and points
   its workers at the same notes file.
4. **Build.** Dispatch one Orca task per ticket in the batch, running the
   [`implement`](~/.agents/skills/implement/SKILL.md) skill's § Build by pointer — the
   issue reference, the notes path, and the branch base, never a summary.
   Seed the worker to stop after committing, report its branch, and wait; the
   coordinator owns review and the PR.
5. **Review.** Once a worker reports its branch, `git fetch` it and review it
   with an in-process subagent (`Agent` tool, `model: opus`) — no Orca task,
   no terminal, no worktree; review is read-only. Seed it with only the issue
   reference and the branch — never the burn history or the explorer's notes —
   running the `~/.agents/skills/code-review/SKILL.md` skill by pointer, not by
   slash invocation. It owns the verdict, one of three:

   - **clean** — go to step 6.
   - **changes requested** — findings the builder can act on. Pass them to the
     builder **verbatim**, in its own worktree, then re-review. This is the
     normal outcome of a first review; it is not a park.
   - **can't get clean** — genuinely blocked: the fix needs a decision the
     coordinator cannot make, or the ticket is wrong. Only this one parks.

   A re-review seed always names the range `<reviewed-sha>..<new-sha>`, never
   just the branch — builders amend and force-push, and a reviewer pointed at a
   branch name silently re-reads work it already cleared. Reviews run
   concurrently and do not count against the builder cap.
6. **Settle, one at a time**, in the order reviews come back clean, per the
   Finish section of `~/.agents/skills/implement/SKILL.md` — which carries the
   ownership gate. Where the repo owner lets agents land directly, land. Where
   review is a human's, the terminal state of a ticket in this burn is **PR
   open**: open it, hand over the exact `gh pr merge` line, and do not merge.
   Satisfy any acceptance criterion the coordinator owns — an issue comment the
   ticket asks for is the coordinator's to post at PR time, and a reviewer's
   correction to its text is a finding like any other.

   On **can't get clean**, park the ticket (below). A worker still mid-build on
   a stale base needs no warning: the PR reports the conflict against the pushed
   default branch, so a real collision surfaces there and parks the ticket.

   Then **tear down the ticket's worktree**. `git status --porcelain` in it
   first and keep it if anything is uncommitted or untracked; otherwise
   `orca-ide worktree rm --worktree name:<name> --force`. Orca does not do this
   on merge, so a burn that skips it leaves a worktree per ticket in the
   sidebar and holds the local branch against deletion.
7. Append to the progress file at
   `~/.cache/burndown/<repo dir name>.progress` (never in the repo), one line
   per state change. A parser reads it, so write **only** these lines:

   ```
   burning #<n>          claimed, build in flight
   #<n> pr <ref>         PR open, awaiting a human merge
   #<n> landed <sha>     merged
   #<n> parked: <why>    handed to a human
   done                  the loop stopped
   ```

   Anything else is counted as nothing: a burn that writes prose here shows as
   permanently building on the statusline. Write `landed` only for a merge that
   happened — when the human owns the merge, `pr` is where the ticket stops.
   Full grammar and the renderer:
   `~/.agents/skills/flow/ccstatusline-table/helpers/burndown-segment.sh`.
8. When a ticket settles, refill its slot: go to 1, skipping step 3. Re-list
   every pass — a landing can unblock tickets, and a human may have added
   more. At the ticket cap — landed plus parked — start no new tasks, let the
   live ones settle, and stop.

## Waiting on Orca workers

Never the Orca wait verb — it returns `waiter_exists` for a waiter nobody can
see and its retry flag does not attach. Use `orca-wait --terminal <handle>
--for exit|tui-idle [--timeout-ms N]` (in `~/.local/bin`), which polls
`terminal show`: exit 0 = met, 2 = timeout. Always pass a timeout, and kill an
old wait loop before arming a new one. Subagents are not waited on this way —
the `Agent` call returns when the subagent finishes.

One consumer of the Run mailbox at a time. `--types` decides when a waiter
wakes, but the delivery it returns is the oldest whole batch, so heartbeats
still arrive and a manual `check` while a waiter is armed drains the batch that
waiter was going to return. Use `check --ack <delivery_id> --wait` as one call,
and treat a heartbeat-only batch as a checkpoint, not an event.

## Coordinator context stays thin

The tracker and the progress file are the state, not this conversation:
re-derive the queue every pass, and keep one line per finished ticket in
context — build detail lives with the worker, review detail in the review
report. A burn survives summarization this way, and a fresh session can
resume a half-done queue from the tracker and progress file alone.

## When a ticket can't land

A park is for a ticket no worker can finish: a stop-and-ask gate or a
non-mechanical conflict with no human answering. Review findings are not a
park — a reviewer's **changes requested** goes back to the builder, however
long the list. To park: **park it** — comment the open question on the issue, swap
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
