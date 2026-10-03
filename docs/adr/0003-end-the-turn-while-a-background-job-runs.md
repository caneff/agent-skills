# End the turn while a background job runs; a mod wakes the session

Status: accepted (ruled by Chris 2026-10-03); the doc change waits on the mod

## Context

Two always-on rules contradict each other about waiting on a background job:

- `flow/claude/OPERATIONS.md` § Wait: "Never go idle waiting on a background
  task: block on it (TaskOutput block=true, or poll in-turn)". Why it was
  written: monitor notifications get lost, and an idle session is not woken
  by a lost one.
- `Memory/RULES.md`: "Never spin a tool call while waiting — no poll loop, no
  `sleep`, no blocking wait … End the turn; its completion wakes you."

## Decision

`RULES.md` wins: a session ends its turn while a background job runs.

The problem the OPERATIONS rule solved, a lost notification leaving an idle
session asleep, stays solved by a mechanism rather than by blocking: a mod
(hooks plugin) that watches `job-run` job directories and wakes the session
when a job exits or its output matches a failure signature
(`Traceback|Error|REJECTED|bad_alloc|Killed`).

## Consequences

- The sentence in `flow/claude/OPERATIONS.md` § Wait, which this ADR retires,
  is rewritten in the same change that ships the wake mod, not before: removing it first would reopen the lost-wake
  failure with nothing behind it.
- Unverified when ruled: whether a mod's `$.prompt.submit` wakes an idle
  session. The mod's ticket probes this first; if it cannot, this ADR
  reopens.
