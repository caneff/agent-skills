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

The coordinator's job is judgment and git surgery over a long session: start
it as `opus`, not the top tier — `sonnet` is the experiment to run once the
cost file (a later ticket) shows the coordinator's own share of the burn.

A single spec's slices in one Orca workspace are
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this skill's.
When the whole queue is one spec's slices, run that instead. When a spec's
slices sit in a mixed queue, this skill hands the spec off to it as one unit —
see § Spec handoff — rather than building the slices one PR at a time.

**Arguments:** `/burndown [builders] [tickets]` — the maximum number of live
worker tasks (default 3) and the maximum number of tickets this burn will
settle (default 15). `/burndown 1` builds strictly one ticket at a time. A
burn stops at the ticket cap even with the queue non-empty; run it again to
continue, since the tracker and the progress file hold all the state.

## Shape

Mirrors `implement-spec`: one Run, one Task per ticket, dependencies as
blocking edges, workers via Orca `claude` at the model exploration's size tag
picks (§ below) — `sonnet` for docs-only and one-file, `opus` for multi-file,
the top tier only when the ticket names it — frontier = Orca's ready-task
query. Unlike `implement-spec`, the
ticket set is not fixed up front — the queue is mixed-origin and re-listed
every pass, so a task is created for a ticket only once it enters the
frontier, and a landing or a human adding tickets can grow the queue mid-burn.

One **exploration** pass, first pass only, covering every ticket this burn
can reach — step 1's listing in dependency order, cut at the ticket cap, not
just the first pass's frontier — that every ticket task depends on. The cap is
sized for this read: at 15 tickets it fits a 200k window with room to think;
past 20 it skims. For each ticket, exploration records a size tag — docs-only
(no code file touched: a SKILL.md, hook, settings.json, or CI config counts as
code per the owner's Gate 2), one-file, or multi-file — in the notes. Notes go
to `~/.cache/burndown/<repo dir name>.notes.md`,
outside the repo so every worker can read them, and are kept after the burn.
A later pass that lists a ticket not in the pass-1 queue explores that ticket
alone and appends to the same file.

Exploration must report **collisions**: any file two tickets in the batch would
both touch. Resolve every collision before dispatching — narrow one ticket's
scope to what its own issue already permits, or serialise the pair — and say in
each builder's seed which files are its own. Two builders editing one file is a
merge conflict the coordinator caused.

Exploration also **checks every grill decision against the code it rests on.**
A ticket's grill comment often overrides its body, and it is written from
memory of how a component behaves. For each decision that asserts runtime
behaviour ("the mask is always on in puzzle mode", "the server resizes before
the switch"), the explorer finds the line that implements it and quotes it in
the notes — confirmed, or contradicted with the file:line. A contradicted
decision is a ruling for the human, posted on the issue before dispatch, not a
P0 for a reviewer to find after the build (#130 cost a build, a review round
and a ruling comment that way).

Exploration is read-only and needs no worktree, terminal, or Orca task: run it
as an in-process `Explore` subagent (`Agent` tool, `model: sonnet`) and read
its result directly. **Only builders are Orca tasks** — they are the only
workers that write code and need their own worktree and branch. Everything
read-only, exploration and review both, is an in-process subagent.

## The loop

The loop's unit is the batch: dispatch every builder in a batch together,
wait, settle every ticket in it, and only then re-list for the next frontier
— there is no per-slot refill (step 8 has the rule). Exploration itself stays
per-burn (step 3), run once regardless of how many batches follow.

1. List the queue: `gh issue list --label ready-for-agent --state open`.
   Empty, with nothing in flight → report and stop.
2. Take the **frontier** via Orca's ready-task query: every ticket whose
   blockers are all closed, lowest numbers first, up to the free worker
   slots. That set is this pass's batch. Before dispatching, pull out any
   ticket that is a sub-issue of a `spec`-labelled parent: those go through
   § Spec handoff as one unit per spec, and the spec takes one worker slot.
3. First pass only: run exploration (above) as a subagent and wait for its
   result before dispatching builders. Every later pass skips this and points
   its workers at the same notes file.
4. **Build.** Dispatch one Orca task per ticket in the batch, running the
   [`implement`](~/.agents/skills/implement/SKILL.md) skill's § Build by pointer — the
   issue reference, the notes path, and the branch base, never a summary.
   Pass the model on `worker-start --model`, from exploration's size tag:
   `sonnet` for docs-only and one-file, `opus` for multi-file, the top tier
   only when the ticket names it.
   Seed the worker to stop after committing, report its branch, and wait; the
   coordinator owns the PR.

   **Docs-only lane.** A docs-only ticket's seed skips `implement`'s
   test-first step and Finish's review step entirely — commit, then report;
   no `code-review`, no `two-axis-code-review`. It still gets its own
   worktree, branch, and progress lines like every other ticket; only the
   seed's build steps shrink. Step 5 never triggers for it — the coordinator
   settles it straight out of this step, with no reviewer.

   For a one-file or multi-file ticket, two more lines go in every seed.
   First: read the
   repo's `CLAUDE.md` and `AGENTS.md` before editing and apply their
   same-PR rules (docs, glossary, CONTEXT.md) — a pointer buried under a
   task list gets skipped, and the reviewer then spends a round on it. Second,
   point the builder at `implement`'s § Finish for its review steps only —
   run both reviews (the built-in `code-review` skill and
   `~/.agents/skills/two-axis-code-review/SKILL.md`) on its own branch, then
   stop short of Finish's own PR step; the coordinator owns the PR, per
   above. The review skills pin their own subagent models, not the
   builder's: `two-axis-code-review/SKILL.md:86` passes `model: opus` to both
   its spawned reviewers regardless of the builder's tier, so a sonnet-tier
   build still gets an opus-tier two-axis review; the built-in `code-review`
   carries no such pin and runs at the builder's own session model. What
   happens to each finding is this burn's rule, not Finish's: act
   on it, then lead the `worker_done` report with every finding both reviews
   raised, one of three dispositions each — **fixed**, **deferred: <why>**,
   or **disputed: <why>** — before the commit sha; a done message with no
   findings list is a question back to the builder, not a settle. One rule
   goes in every seed: a question
   to the coordinator that times out is not a stop — take the safe option, the
   one a reviewer can reverse in a single commit, keep building, and put the
   question and the choice you made at the top of `worker_done`. The
   coordinator's attention is not a dependency a build may block on.

   After every `worker-start`, run `git -C <worktree> branch --show-current`
   and confirm it names the ticket's own branch. Reusing a just-removed
   worktree name, or starting from `--base-branch <other ticket's branch>`,
   has left Orca checking out the base branch itself, so the builder would
   have committed onto another ticket's PR. Fix it with `git checkout -b`
   before the worker's first commit and tell the worker.

   **Do not `worker-release` at `worker_done`.** The builder stays live until
   its ticket settles or parks — whether or not a review round happens: when
   one does, findings go to its dispatch (`orchestration send --to
   dispatch:<id>`), so a fix round costs no Orca startup and no re-reading of
   the ticket and notes. Release at settle (reviewed or skipped straight from
   step 5) or when the ticket parks, never before.

   The coordinator's wait, from here through settle, covers `question` and
   `escalation` alike, not just `worker_done` — a blocking question is real
   and needs an answer; only the status-poll workaround for finding one is
   moot now that there's no task-list poll to miss it (§ Waiting on Orca
   workers has the one-wait-per-wake mechanics).
5. **Review.** A docs-only ticket never reaches this step — § 4's docs-only
   lane settles it straight into step 6 with no reviewer. For a one-file or
   multi-file ticket, the coordinator spawns its own in-process reviewer only
   on one of two triggers: the builder's report defers or disputes a finding, or the
   branch's changed files (`git diff --name-only <range>`, checked against
   the seed's own-files list from § Shape) leave the set exploration assigned
   to the ticket. A report with every finding fixed and no file outside its
   set skips review and goes straight to step 6.

   When triggered, `git fetch` the branch and review it with an in-process
   subagent (`Agent` tool, `model: opus`) — no Orca task, no terminal, no
   worktree; review is read-only. Seed it with three things only — the issue
   reference, the builder's `worker_done` report, and the commit range —
   never the burn history or the explorer's notes: this reviewer is
   confirming a specific gap, not re-reading the ticket from scratch. It runs
   the same two reviews step 4 names, by pointer, not by slash
   invocation — correctness first, then spec/standards. The seed says: run
   `code-review` in your own context, never as a background fork — a forked
   review hung twice in one burn and needed two pings before it returned;
   wait for both reviews to finish, then send the verdict with the message
   tool **before** going idle, and arm no background wait afterwards — a
   reviewer that keeps a timer running re-notifies the coordinator with the
   same verdict two or three times, and one that goes idle without sending
   costs a round trip to prod it. The coordinator prods a silent reviewer
   once, then rules on the findings it already has. It owns the verdict, one
   of three:

   - **clean** — go to step 6.
   - **changes requested** — findings the builder can act on. Write them to
     `~/.cache/burndown/findings/<n>-r<round>.md` **verbatim** and send the
     path to the builder's live dispatch, then re-review.
   - **can't get clean** — genuinely blocked: the fix needs a decision the
     coordinator cannot make, or the ticket is wrong. Only this one parks.

   This gets exactly **one round**: a re-review, if the fix needs checking,
   always **resumes the same reviewer** (send it the range with the message
   tool) rather than spawning a fresh one — a resumed reviewer checks its own
   list and stops, while a fresh reader re-reads the whole branch and grades
   comment wording as P1 — and the re-review message names the range
   `<reviewed-sha>..<new-sha>`, never just the branch, since builders amend
   and force-push and a reviewer pointed at a branch name silently re-reads
   work it already cleared. Whatever is still open after that one round goes
   into the PR body for the human, not into a second round. Reviews run
   concurrently and do not count against the builder cap.
6. **Settle**, in the order each ticket clears — reviewed clean or skipped
   straight from step 5 — per the
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
   Several `burning` lines can be open at once, one per ticket in flight; a
   ticket's state is its last line, so a later line supersedes an earlier one
   for that ticket — `pr` followed by `landed` is one ticket, merged.
   This is the single documented home for the grammar — nothing else restates it.
8. Once every ticket in the batch has settled or parked, re-list the queue
   for the next frontier: go to 1, skipping step 3. Re-list every pass — a
   landing can unblock tickets, and a human may have added more. There is no
   per-slot refill: a settled ticket's slot sits idle until every ticket in
   its batch has settled or parked, so the frontier taken in step 2 is always
   a whole batch, not a trickle of one-off replacements. Parks stay immediate
   and never hold the batch: a parked ticket gets its progress line and its
   issue comment right away, but the loop still waits on its batch-mates
   before re-listing. At the ticket cap — landed plus parked — start no new
   tasks, let the live ones settle, and stop.

## Spec handoff

A ticket whose parent issue carries the `spec` label is a slice, and slices
are built together or not at all: one workspace, one branch, one PR that
closes the spec and every child, with the end-to-end review loop that only
`implement-spec` runs. Building them one PR at a time here loses that loop and
lands a spec in pieces a human has to reassemble.

So the spec, not the slice, is the unit. Find the parent with
`gh api repos/<owner>/<repo>/issues/<n>/parent` (or the `Part of #N`
reference in the body when the tracker has no sub-issues) and confirm its label.
Then:

- Make one Orca workspace **from the spec issue** and dispatch one Orca task
  in it — a top-level `claude` session seeded with the spec URL and the pointer
  `~/.agents/skills/implement-spec/SKILL.md`, which it follows as coordinator.
  That coordinator owns the spec's exploration, frontier, gates, review loop,
  and PR; this burn does not look inside.
- Every open slice of that spec — ready or still blocked — leaves this burn's
  queue at handoff, and the cluster counts against the ticket cap as its
  number of slices. Slices already `in-progress` under a burn worker finish
  as they are; the spec coordinator picks up from their landings.
- Progress lines use the spec's number: `burning #<spec>`, then `#<spec> pr
  <ref>` or `#<spec> parked: <why>`. A gate the spec coordinator raises is that
  burn's `ready-for-human` for the whole spec — park it, do not answer it.
- The spec's workspace is the coordinator's to tear down, not this burn's.

A slice with no `spec`-labelled parent is an ordinary ticket. A spec with
exactly one open slice is still handed off — the loop is the point, not the
count.

## Waiting on Orca workers

Never the Orca wait verb — it returns `waiter_exists` for a waiter nobody can
see and its retry flag does not attach. Use `orca-wait --terminal <handle>
--for exit|tui-idle [--timeout-ms N]` (in `~/.local/bin`), which polls
`terminal show`: exit 0 = met, 2 = timeout. Always pass a timeout, and kill an
old wait loop before arming a new one. Subagents are not waited on this way —
the `Agent` call returns when the subagent finishes.

One consumer of the Run mailbox at a time, and one wait per wake: every wake
is a single `check --ack <delivery_id> --wait` call, acknowledging the prior
delivery in the same call, with no `task-list` poll before or after it —
`worker-start` branch checks and progress-file writes happen around that one
call, not a status loop between wakes. `--types` decides when a waiter wakes,
but the delivery it returns is the oldest whole batch, so heartbeats still
arrive inside it; treat a heartbeat-only batch as a checkpoint, not an event,
and go straight into the next `check --ack --wait` rather than polling task
status to fill the gap.

The mailbox waiter lives on the server, not in the client. A `check --wait`
that is backgrounded, killed, or interrupted leaves its waiter armed, and every
later wait fails with `waiter_exists` until that waiter's own timeout expires —
so run `check --wait` in the foreground only, with a timeout long enough to
cover a real wait but short enough to survive a kill (five minutes, never the
tool's maximum), and when one is stuck poll with `check --peek` until it
clears rather than retrying the wait.

## Coordinator context stays thin

The tracker and the progress file are the state, not this conversation:
re-derive the queue every pass, and keep one line per finished ticket in
context — build detail lives with the worker, review detail in the review
report. A burn survives summarization this way, and a fresh session can
resume a half-done queue from the tracker and progress file alone.

The same holds one level down: the work is in the worktree, not in the worker.
An Orca restart that kills a builder and stales its terminal handle leaves the
diff on disk, so re-dispatch a fresh worker into that same worktree, seeded to
judge the uncommitted diff it adopts — accept it, fix it, or throw it out —
rather than to restart the ticket.

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

Where a human owns the merge, the report ends with **one pasteable line** that
merges every PR from this burn, leading with `cd <absolute repo path> &&` and
carrying `--repo owner/name` on every `gh` call:

```
! cd <repo> && for n in <PR numbers>; do gh pr merge $n --repo <owner/name> --squash --delete-branch; done
```

Before handing it over, dry-run merge every branch in that order onto the
default branch in a detached throwaway worktree and run the repo's test seam;
say the result in one line. Never split the merges into per-PR commands. Any
post-merge step a human must do on the live machine follows the line, in
order.

**Branches that conflict with each other get linearised, not squashed.** Two
PRs that touch the same line (an import list, a scenario count) both merge
clean against the default branch and then conflict with each other after the
first squash, so the one-line merge stops halfway. When the dry run shows
that, rebase the later branches into one linear stack in merge order,
resolving only the shared line, verify each rebased branch's diff is identical
to its reviewed diff apart from that line, run the seam at the stack tip,
force-push (with lease), note the new base sha in each PR body, and hand the
line with `--merge` in place of `--squash` — merge commits keep a linear stack
mergeable in one line, squashes do not. Every PR still opens against the
default branch, never against its base branch: GitHub closes a PR whose base
branch is deleted and cannot reopen it. Prefer not stacking at all: when other
tickets are ready, hold the serialised ticket until its base lands, and stack
only when the slot would otherwise sit idle.

**Live verification is batched, not per ticket.** A ticket whose sign-off
needs the live rig (a scene shot to eyeball, a stream-side behaviour to watch)
cannot be verified inside the burn, and the burn must not start a live run
on its own. Do not repeat "confirm on the next live run" once per PR. The
report ends with one **post-burn live check** step that lists every such
item, so a single run after the merges clears them all.
