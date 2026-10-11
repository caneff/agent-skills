# Does a `run_in_background` Bash call have a wall-clock cap?

**No cap at 30 minutes; one is not ruled out past about 3 hours.** Measured
2026-10-11 for #1223, which needed this before building `job-run --wait`.

## What was counted

Every transcript under `~/.claude/projects` (JSONL). A **launch** is a Bash
`tool_use` with `run_in_background: true` whose result carries a
`backgroundTaskId` and no `timedOutAfterMs` (so an auto-backgrounded foreground
call and a Monitor are out). Its **end** is the first later record holding that
task id and `<status>completed</status>`. Launches with no such record in the
same transcript are not counted.

## Result

| | count |
| --- | ---: |
| explicit background Bash launches that reached `completed` | 1001 |
| of those, lasting over 1800 s | 22 |
| longest | 10818 s (about 3 h) |

A second scan by a review subagent found 1019, 22 and 10817 s, so the figures
are stable to the counting rule.

## What it does not show

The sample ends at about 3 h, so a cap above that is not ruled out; the
[older note](2026-09-19-background-task-terminal-states.md)'s 104446 s maximum
pools background shells with auto-backgrounded calls and Monitors and is not
evidence for this class alone. A task torn down with no marker (45% of launches
there) is absent from both counts.
