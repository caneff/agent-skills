# Phase timings per ticket, from worker transcripts (#826)

Read out of each worker's main-line Claude transcript with
`burndown/phases.py <ticket-number>`, beside `burndown/cost.py`. Method:
`burndown/phases.py`'s own docstring and `phases_test.py` say what each
phase boundary means; this file is the output, not the tool.

Two corrections the tool forced, both caught by the `multi-axis-code-review`
Correctness pass reading this ticket's own diff — worth naming since they're
exactly the kind of self-referential trap a transcript-mining tool falls into:

- An `Agent` tool call's own `tool_result` on the main line only
  acknowledges the async launch, a couple of seconds after the call — not
  the subagent finishing. The real finish time is the last timestamp in
  that subagent's own transcript, `<session>/subagents/agent-*.jsonl`,
  whose sibling `.meta.json` carries the `toolUseId` linking it back. Reading
  the async-ack instead (my first pass) undercounted every review-phase
  duration by roughly 10x.
- `pr_open` and `report` were first matched by bare substring
  (`"gh pr create" in command`, `"pr up" in message`). Both false-positived
  on this very ticket: a `python3 -c` heredoc inspecting past Bash calls
  contains the literal string `"gh pr create"`, and an early planning
  message ("#824 ... before PR up ... has no Seams") contains "pr up"
  mid-sentence. Both are now anchored — `gh pr create` must start its own
  command segment, `pr up` must start the message (the worker's actual
  report always does, by convention).

## Table

All durations in minutes. `build offset` = dispatch → first Edit/Write.
`total` = dispatch → the "PR up" `SendMessage` finishing send — blank where
`report` was never reached. `waiting` = total time from an outgoing
`SendMessage` to the next incoming cross-session message (§ ticket body).

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
| 819 | 16.1 | 0.6 | 4.3 | 2.1 | 0.0 | 3.6 |
| 820 | 26.1 | 2.6 | 3.9 | 4.2 | 0.1 | 0.0 |
| 821 | 12.7 | 2.2 | 3.5 | 2.2 | 0.0 | 4.1 |
| 822 | 11.4 | 1.2 | 2.1 | 1.6 | 0.1 | 3.9 |
| 824 | 5.6 | 1.3 | 1.8 | — | 0.0 | 5.8 |
| 367 (sudokumaker) | 21.7 | 3.1 | 3.2 | 2.9 | 0.1 | 0.4 |
| 368 (sudokumaker) | 87.6 | 4.2 | 4.6 | 22.7 | 0.1 | 31.3 |

`824`'s `verification` is blank: its round-1 review found nothing to fix,
so there was no second review invocation to time — not a gap in the tool.

## Reading it

- **Median total, dispatch → PR up: 14.4 min** across these 15 tickets —
  dominated by build time, not review. Review round 1 (three parallel axis
  reviews) plus verification together run 2–10 min on a typical ticket;
  they rarely gate the worker, which keeps building or waits concurrently
  rather than blocking on them.
- The ticket's own opening estimate — "first commit → PR open at a median
  of ~8 min" — used git commit timestamps, not the transcript. Measured
  from the transcript's first Edit/Write tool call to the `gh pr create`
  call, the median across these 15 is **13.7 min**, not 8. The gap is
  consistent with "first commit" landing well after "first edit" (reading,
  exploring, false starts before anything is staged) rather than a
  contradiction of the estimate.
- **#812 (39.3 min) and #368 (87.6 min) are the outliers**, both on
  `verification`, not `review_round_1`: #812's verification pass ran 15.2
  min, #368's 22.7 min plus 31.3 min waiting on the controller after — a
  single verification round, scoped to round-1 findings and fix commits,
  can itself take longer than the first review round when there's a lot to
  re-check.
- **Six tickets show real controller-wait time** (817, 819, 820\*, 821,
  822, 824, 367, 368) once the incoming-message detector was fixed to
  require a plain-text envelope rather than substring-matching any
  serialized content (§ corrections above) — several of these read as 0.0
  before that fix, undercounting a wait a false "reply" had closed early.
  \*820's own wait rounds to 0.0 at one decimal (a few seconds); every
  other ticket not listed here never blocked on a controller reply long
  enough to register.
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
tests (`phases_test.py`). A ticket number matching more than one repo's
worktree (rare) gets a disambiguated `<n>:<project-dir>` identifier instead
of colliding under one row.
