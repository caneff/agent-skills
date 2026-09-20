---
name: burndown
description: "Parked: drain a mixed-origin ticket queue to empty as one supervised run, frontier-first, one PR per ticket."
disable-model-invocation: true
---

> **Parked** until the multi-worker lane is rebuilt on the herdr lane — see
> [#700](https://github.com/caneff/agent-skills/issues/700)'s "Out of scope"
> note. Everything this skill described — the batch loop, exploration and
> clumping, worker dispatch, the review round, and the progress and cost
> bookkeeping — is retired with the tool it ran on; nothing below is
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

A single spec's slices in one workspace are
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this
skill's — also parked.
