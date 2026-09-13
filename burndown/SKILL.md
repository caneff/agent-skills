---
name: burndown
description: "Parked: drain a mixed-origin ticket queue to empty as one supervised run, frontier-first, one PR per ticket."
disable-model-invocation: true
---

> **Parked** until the multi-worker lane is rebuilt on the herdr lane — see
> [#700](https://github.com/caneff/agent-skills/issues/700)'s "Out of scope"
> note. Nothing below is executable policy until then.

A single spec's slices in one workspace are
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this
skill's — also parked.

## Shape

Parked — the one-Run task graph, the shallow/deep exploration passes, the
collision clumping step, and the frontier-based worker dispatch described
here belonged to the retired coordination tool.

## The loop

Parked — the eight-step batch loop (list, take the frontier, explore, build,
review, settle, log progress, re-list) belonged to the retired coordination
tool.

## Docs-only lane

Parked — the shortened seed for a docs-only ticket belonged to the retired
coordination tool's dispatch step.

## Holding the builder

Parked — holding a dispatched worker live across a fix round, and mid-build
addenda, belonged to the retired coordination tool.

## Waiting on workers

Parked — the wait primitive here belonged to the retired coordination tool.

## Coordinator context stays thin

Parked — this described how the coordinator re-derived state from the
tracker and progress file rather than its own context; the coordinator role
it describes is retired with the lane.

## When a ticket can't land

Parked — parking a ticket mid-burn (open question, no landing) belonged to
the retired coordination tool's loop.

## Report

Parked — the end-of-burn tally and the pasteable merge line belonged to the
retired coordination tool's loop.
