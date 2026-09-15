# Phase timings per ticket, from worker transcripts (#826)

Read out of each worker's main-line Claude transcript with
`burndown/phases.py <ticket-number>`, beside `burndown/cost.py`. Method:
`burndown/phases.py`'s own docstring and `phases_test.py` say what each
phase boundary means; this file is the output, not the tool. Regenerated
from the shipped code after review — see "Corrections" below for what
changed and why, so the numbers here are traceable rather than a black box.

## Corrections

Three rounds of review on this ticket's own diff caught four bugs, each
because the tool's own transcript (or this doc) was itself fed through it:

- An `Agent` tool call's own `tool_result` on the main line only
  acknowledges the async launch, a couple of seconds after the call — not
  the subagent finishing. The real finish time is the last timestamp in
  that subagent's own transcript, `<session>/subagents/agent-*.jsonl`,
  whose sibling `.meta.json` carries the `toolUseId` linking it back.
  Reading the async-ack instead (the first pass) undercounted every
  review-phase duration by roughly 10x.
- `pr_open` and `report` were first matched by bare substring
  (`"gh pr create" in command`, `"pr up" in message`). Both false-positived
  on this very ticket: a `python3 -c` heredoc inspecting past Bash calls
  contains the literal string `"gh pr create"`, and an early planning
  message ("#824 ... before PR up ... has no Seams") contains "pr up"
  mid-sentence. Both are now anchored — `gh pr create` must start its own
  command segment, `pr up` must start the message (the worker's actual
  report always does, by convention).
- `verification` was first matched by a `"verif"` keyword in the Agent
  call's description/prompt, not by the ticket's own definition — "the
  second review invocation." A Codex adversarial-review pass on this PR
  caught the consequence directly: on ticket #812 the keyword match landed
  on the *first* axis call whose description happened to contain "verif",
  reporting a 913-second verification span that started before round 1 had
  even finished. Verification is now classified ordinally — the Agent
  spawns are clustered by a 120-second gap (clean on every ticket in this
  table: every within-round gap is under 17s, every real gap to the next
  round is over 250s), and the second cluster is verification regardless
  of wording.
- `waiting_on_controller` paired every outgoing `SendMessage` with the next
  incoming cross-session message, including the "PR up" report itself —
  which isn't a question awaiting a reply. On #820 this undercounted a
  genuine 26.4-minute wait as 0.0 (a later, unrelated incoming message
  closed the pairing early) and on #824 it overcounted by pairing the
  report with the next message regardless of relevance. Fixed: a "PR up"
  report is excluded from starting a wait.

## Table

All durations in minutes. `build offset` = dispatch → first Edit/Write.
`total` = dispatch → the "PR up" `SendMessage` finishing send. `waiting`
= time from an outgoing `SendMessage` that isn't a "PR up" report to the
next incoming cross-session message.

| ticket | total | build offset | review round 1 | verification | pr open | waiting on controller |
|---|---|---|---|---|---|---|
| 801 | 14.4 | 0.8 | 4.0 | 2.6 | 0.1 | 0.0 |
| 803 | 12.7 | 0.3 | 2.5 | 2.5 | 0.1 | 0.0 |
| 805 | 10.5 | 1.1 | 3.4 | 1.7 | 0.0 | 0.0 |
| 808 | 14.2 | 0.3 | 3.8 | 2.2 | 0.1 | 0.0 |
| 810 | 10.9 | 0.4 | 3.1 | 2.4 | 0.0 | 0.0 |
| 812 | 39.3 | 0.7 | 7.4 | 2.4 | 0.0 | 0.0 |
| 814 | 22.1 | 2.0 | 10.1 | 1.7 | 0.0 | 0.0 |
| 817 | 23.7 | 1.3 | 3.7 | 2.9 | 0.1 | 0.0 |
| 819 | 16.1 | 0.6 | 4.3 | 2.1 | 0.0 | 1.4 |
| 820 | 26.1 | 2.6 | 3.9 | 4.2 | 0.1 | 26.4 |
| 821 | 12.7 | 2.2 | 3.5 | 2.2 | 0.0 | 0.0 |
| 822 | 11.4 | 1.2 | 2.1 | 1.6 | 0.1 | 3.5 |
| 824 | 5.6 | 1.3 | 1.8 | — | 0.0 | 5.8 |
| 367 (sudokumaker) | 21.7 | 3.1 | 3.2 | 2.9 | 0.1 | 0.0 |
| 368 (sudokumaker) | 87.6 | 4.2 | 7.0 | 6.5 | 0.1 | 31.3 |

`824`'s `verification` is blank: its round-1 review found nothing to fix,
so there was no second invocation to time — not a gap in the tool.

## Reading it

- **Median total, dispatch → PR up: 14.4 min** across these 15 tickets.
  Review round 1 plus verification together are a **median 40% of that
  total** (15–53% across tickets, `review_round_1 + verification` divided
  by `total`) — a real share of wall-clock, not a rounding error, though
  rarely the majority. The worker session sits and waits for the axis
  agents rather than doing other useful work in parallel (see #817's own
  transcript: "I'll just wait passively for the next task notification
  instead of polling"), so this is real serial time on the critical path,
  not overlapped-and-free.
- The ticket's own opening estimate — "first commit → PR open at a median
  of ~8 min" — used git commit timestamps, not the transcript. Measured
  from the transcript's first Edit/Write tool call to the `gh pr create`
  call, the median across these 15 is **13.7 min**, not 8. The gap is
  consistent with "first commit" landing well after "first edit" (reading,
  exploring, false starts before anything is staged) rather than a
  contradiction of the estimate.
- **#812 and #368 have the longest review_round_1** (7.4 and 7.0 min) of
  the corpus, but neither dominates its ticket's total the way the earlier,
  keyword-classified numbers suggested — #812's real bottleneck (39.3 min
  total) is elsewhere in the unlabeled build/fix time between phases, not
  in review or verification.
- **Three tickets show real controller-wait time**: #820 (26.4 min — the
  single largest number in this table, previously misread as 0.0 by the
  report-pairing bug above), #368 (31.3 min), and smaller waits on #819,
  #822, #824. Every other ticket never blocked on a controller reply long
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
