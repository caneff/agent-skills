# Phase timings per ticket, from worker transcripts (#826)

Read out of each worker's main-line Claude transcript with
`burndown/phases.py <ticket-number>`, beside `burndown/cost.py`. Method:
`docs/research/2026-09-15-phase-timings.md` (this file) is the output, not
the tool — see `burndown/phases.py`'s own docstring and `phases_test.py`
for what each phase boundary means.

One correction the tool forced: an `Agent` tool call's own `tool_result` on
the main line only acknowledges the async launch, a couple of seconds after
the call — not the subagent finishing. The real finish time is the last
timestamp in `<session>/subagents/agent-*.jsonl`, whose sibling
`.meta.json` carries the `toolUseId` linking it back to the call. Reading
the async-ack instead (my first pass) undercounted every review-phase
duration by roughly 10x.

## Table

All durations in minutes. `build offset` = dispatch → first Edit/Write.
`total` = dispatch → the "PR up" `SendMessage` finishing send. `waiting`
= total time from an outgoing `SendMessage` to the next incoming
cross-session message (§ ticket body). `820` was still mid-review when this
table was built — its PR was never opened in this transcript, so `total`,
`verification` and `pr open` are blank, not zero.

| ticket | total | build offset | review round 1 | verification | pr open | waiting on controller |
|---|---|---|---|---|---|---|
| 801 | 14.4 | 0.8 | 4.0 | 2.6 | 0.1 | 0.0 |
| 803 | 12.7 | 0.3 | 2.5 | 2.5 | 0.1 | 0.0 |
| 805 | 10.5 | 1.1 | 1.3 | 6.7 | 0.0 | 0.0 |
| 808 | 14.2 | 0.3 | 3.8 | 2.2 | 0.1 | 0.0 |
| 810 | 10.9 | 0.4 | 3.1 | 2.4 | 0.0 | 0.0 |
| 812 | 39.3 | 0.7 | 7.4 | 15.2 | 0.0 | 0.0 |
| 814 | 22.1 | 2.0 | 10.1 | 1.7 | 0.0 | 0.0 |
| 817 | 23.7 | 1.3 | 3.7 | 2.9 | 0.1 | 6.1 |
| 819 | 16.1 | 0.6 | 4.3 | 2.1 | 0.0 | 0.3 |
| 820 | — | 2.6 | 3.9 | — | — | 11.6 |
| 821 | 12.7 | 2.2 | 3.5 | 2.2 | 0.0 | 1.6 |
| 822 | 11.4 | 1.2 | 2.1 | 1.6 | 0.1 | 1.3 |
| 367 (sudokumaker) | 21.7 | 3.1 | 3.2 | 2.9 | 0.1 | 0.4 |
| 368 (sudokumaker) | 87.6 | 4.2 | 4.6 | 22.7 | 0.1 | 31.3 |

## Reading it

- **Median total, dispatch → PR up, excluding the still-running #820:
  14.4 min** across the 13 finished tickets — dominated by build time, not
  review. Review round 1 (three parallel axis reviews) plus verification
  together run 4–10 min on a typical ticket; they very rarely gate the
  worker, since the worker keeps building/waiting concurrently rather than
  blocking.
- The ticket's own opening estimate — "first commit → PR open at a median
  of ~8 min" — used git commit timestamps, not the transcript. Measured
  from the transcript's first Edit/Write tool call to the `gh pr create`
  call, the median across these 13 is **13.7 min**, not 8. The gap is
  consistent with "first commit" landing well after "first edit" (reading,
  exploring, and false starts before anything is staged) rather than a
  contradiction of the estimate.
- **#812 (39.3 min) and #368 (87.6 min) are the outliers**, both on
  `verification`, not `review_round_1`: #812's verification pass ran 15.2
  min, #368's 22.7 min plus 31.3 min waiting on the controller after — a
  single verification round, scoped to round-1 findings and fix commits,
  can itself take longer than the first review round when there's a lot to
  re-check.
- **#817 and #820 are the only two with real controller-wait time** (6.1
  and 11.6 min) — every other ticket's worker never blocked on a
  controller reply long enough to register. `waiting_on_controller` pairs
  each outgoing `SendMessage` with the next incoming cross-session message
  chronologically; a ticket with none printed 0.0, not a missing value.
- The ~4 h-of-8.5 h sudokumaker "one unsent report" loss the ticket cites
  is not in this table: it isn't `implement-367` or `implement-368` — those
  two are ordinary-length builds (21.7 and 87.6 min total). Whatever
  transcript that anecdote came from isn't named `implement-36*` and this
  run didn't go looking for it beyond the pattern the ticket named.

## Tool

`burndown/phases.py <worktree-path|ticket-number>...` — one line per phase
per ticket: `<identifier> <phase> <start-iso|-> <duration-seconds|->`, plus
a `waiting_on_controller` line. Read-only, same convention as `cost.py`
beside it. `BURNDOWN_PROJECTS_DIR` overrides `~/.claude/projects` for
tests (`phases_test.py`).
