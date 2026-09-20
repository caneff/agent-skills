---
name: burndown
description: "Parked: drain a mixed-origin ticket queue to empty as one supervised run, frontier-first, one PR per ticket."
disable-model-invocation: true
---

> **Parked** until the multi-worker lane is rebuilt on the herdr lane — see
> [#700](https://github.com/caneff/agent-skills/issues/700)'s "Out of scope"
> note. Everything this skill described — the batch loop, exploration and
> clumping, worker dispatch, the review round, and the per-repo progress and
> cost bookkeeping — is retired with the tool it ran on; nothing below is
> executable policy until the lane is rebuilt. Full text:
> `git show 7c7eb30:burndown/SKILL.md`.

## The loop

The dispatch loop — pick the next jobs, start them, wait, start more as slots
free up — lives **here and nowhere else** (#779). Its mechanical steps are
`burndown/loop.py`; why each rule reads the way it does, with the evidence it
came from: [`references/loop.md`](references/loop.md). Written against the
lane being rebuilt, and parked with the rest of this skill.

**Where the controller runs.** Any primary checkout's **default branch** —
read from `refs/remotes/origin/HEAD`, never assumed to be `main` — and not
necessarily the target repo's checkout: the loop addresses the target with
`--repo` on every tracker call. `python3 burndown/loop.py seat` refuses a
linked worktree and says why, because inside one `/implement`'s front-door
rule reads the session as a **worker** and the same prompt would start a
build instead of a run. It refuses a detached HEAD and a non-default branch
too.

**Open the run.**

1. Take the seat (above), then `runfile.py start` the run with its slot
   budget and the controller's own herdr agent name (§ Run state). Resuming
   an existing run instead: `runfile.py resume`, and then **one message per
   live, unlanded worker** — its `announce` bucket and only that one, via
   `loop.announce`. A landed clump's worker gets none however its agent
   looks; a vanished one gets none either, and is reconciled or parked by
   hand. The bucket names each worker by its **herdr agent name**, which is
   the durable key and not an address: resolve it to a reachable session at
   **send time** (#923), and never write a resolved address into the run
   file.
2. Read the frontier (§ The frontier) over the **whole queue**, not the first
   wave's worth, and clump it (§ Clumping). That exploration is the run's
   **frozen** candidate set: a ticket filed while the run is going waits for
   the next run. The one exception is a ticket filed *during* the run
   **because the run is stuck on what it fixes** — `loop.admit` takes it only
   with the clump it unblocks named.
3. The **opening report** carries `closure.py`'s announcement line verbatim,
   so the reader can tell all three declaration states apart: a declared
   directive, a **declared None** — the repo has no include graph — and
   **silence**, which clumps conservatively by directory subtree. A
   controller reading "conservative" has to know which of the last two it
   got.

**Then, until the queue and the slots are both empty:**

4. **Recompute the frontier at each landing** and dispatch into every free
   slot. Refill is **continuous**: no waves, because a wave holds slots
   empty waiting for its slowest clump.
5. **At each dispatch, re-resolve that clump's closure** against current
   `main` — **one hop** — and check it against every **in-flight** workspace.
   A clump whose closure intersects a live workspace's is **off the
   frontier**: `loop.py dispatch` picks from what is left and names what
   holds the rest. Two consequences, stated because neither is visible from
   the frontier's own definition — a run drains **out of ticket order**, and
   on a repo with one hot shared file a single parked worker can hold a
   **whole family** of tickets off the frontier until it lands. A controller
   reading only "open, unblocked, unclaimed" would dispatch into the
   collision.
6. **Full re-exploration fires on one trigger**: a landing whose diff touched
   a **hub** — a file two or more candidates' closures share
   (`loop.py hub`). Every other landing gets step 5's one-hop re-resolution
   and nothing more.
7. **Box check before every dispatch** — `uptime` and `free -g` against the
   **28**-process cap, counting every process on the shared box rather than
   this run's, and the ~**24 GB** ceiling on the sum of the per-process
   `ulimit -v` caps (`loop.py box`). A refusal holds the slot empty; it is
   not a reason to dispatch anyway.
8. Dispatch and merge through
   [`implement`](~/.agents/skills/implement/SKILL.md) § Dispatch, which
   claims the clump and starts the worker; `implement/SKILL.md` § The merge,
   which merges and cleans up, is the controller's own step there. The loop
   restates neither grammar. Record each landing with `runfile.py land`, so a
   restart can pick the run back up.

## The frontier

Which tickets a run may dispatch next — open, labelled, unclaimed, waiting on
nothing — is read by `burndown/frontier.py`, not by a regex at the call site:
`python3 burndown/frontier.py <owner/repo> <label>` prints the `unblocked`,
`blocked` and `unresolved` buckets. Native tracker dependencies first, the
`## Blocked by` section as the fallback, and a ticket with neither is
**unresolved** — never dispatched on the assumption that silence means clear.
The grammar and the three sources:
[`references/frontier.md`](references/frontier.md).
Written against the lane being rebuilt; the loop that will call it is parked
with the rest of this skill.

## Clumping

Which candidates are one clump — one worker, one workspace, one PR — is read
by `burndown/closure.py`, not from the tickets' declared seams:
`python3 burndown/closure.py <repo-root> <n>=<path>[,<path>]...` prints the
mode and the connected components of the collision graph over each
candidate's **include closure**. The repo declares its include directive and
its generator command in `AGENTS.md`; the resolver follows that declaration
one hop and **never runs the generator**. A repo that declares nothing is
clumped conservatively by directory subtree, and the run's **opening report
carries the announcement line** the reader returns, so a controller can see
which of the three modes it got. The grammar and the evidence:
[`references/closure.md`](references/closure.md).

## Run state

A run's state is **one JSON file per run** at `~/.cache/burndown/<run-id>.json`,
read and written by `burndown/runfile.py` — not the controller's context, and
not a per-repo log. It holds the run id, the slot budget, the controller's
herdr agent name, and per clump its ticket list, workspace, worker's herdr
agent name and squash sha once it lands. `runfile.py resume <run-id> --live
<names> --controller <my agent name>` reads it back and splits the clumps into
the live workers to **re-announce** the controller to, the vanished ones to
reconcile by hand, and the landings already banked — the live names read off
the machine, never off the file.

A worker is addressed by its **herdr agent name** throughout, because a WSL
restart renames every Claude session and every brief hard-codes
`--controller "<name>"`. The retired per-repo `~/.cache/burndown/<repo>.progress`
file is gone; nothing reads or writes one. The contract, the JSON shape and the
resume procedure: [`references/run-file.md`](references/run-file.md).
Written against the lane being rebuilt; the loop that will drive it is parked
with the rest of this skill.

A single spec's slices in one workspace are
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this
skill's — also parked.
