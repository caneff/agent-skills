---
name: implement-spec
description: "Parked: drive a sliced spec as one supervised run, workers on the ready frontier, one PR, a review loop until clean."
disable-model-invocation: true
---

> **Parked** until the multi-worker lane is rebuilt on the herdr lane — see
> [#700](https://github.com/caneff/agent-skills/issues/700)'s "Out of scope"
> note. Everything this skill described — the spec-wide task graph, worker
> dispatch, wait, gates, and the end-of-spec review loop — is retired with
> the tool it ran on; nothing below is executable policy until the lane is
> rebuilt. Full text: `git show 7c7eb30:implement-spec/SKILL.md`.

A mixed-origin queue — several tickets from different specs, not one spec's
slices — is [`burndown`](../burndown/SKILL.md)'s job, also parked.
