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
