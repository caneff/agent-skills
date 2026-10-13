# End the turn while a background job runs; a mod wakes the session

Status: accepted (ruled by Chris 2026-10-03); complete 2026-10-13, when the
`job-wake` mod shipped (#1371)

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
  was to be rewritten in the same change that ships the wake mod, not before:
  removing it first would reopen the lost-wake failure with nothing behind
  it. That is not what happened. The section was rewritten on 2026-10-04, nine
  days before the mod. `job-run --wait` (#1223) was the only thing behind it
  from 2026-10-11, and nothing was before that.
- The mod is `flow/mods/job-wake/` (#1371). The section now names it, and keeps
  `job-run --wait` for a session the mod is not loaded in.
- The rule the Context quotes from `Memory/RULES.md` has since moved to
  `flow/claude/CLAUDE.md` § Work.
- `job-run` records the session that started each run, in the run
  directory's `session` file, which is how the mod knows a job is its own.
- Unverified when ruled: whether a mod's `$.prompt.submit` wakes an idle
  session. It does: `docs/research/2026-10-12-mod-wakes-idle-session.md`
  (#1367), and in a herdr pane, including a session parked on a permission
  dialog, `docs/research/2026-10-13-job-wake-live-check.md`.
