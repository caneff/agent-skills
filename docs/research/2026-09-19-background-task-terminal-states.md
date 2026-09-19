# Background tasks often never report a terminal state

Measured 2026-09-19 over every transcript under `~/.claude/projects`
(252 files), while deciding how wide the `worker-stop-alert.sh` "still
out" set may be (#886, #900).

## What was counted

A **launch** is a `toolUseResult` carrying `backgroundTaskId` (a Bash with
`run_in_background`, or a foreground Bash auto-backgrounded at its timeout)
or `taskId` (a `Monitor`). A **terminal state** is a `<task-id>`
task-notification that also carries a `<status>` (`completed`, `failed`,
`killed`, `stopped`), or a `TaskStop` tool call naming that id. Monitor
*event* notifications carry a `<task-id>` and no `<status>`, so they are not
terminal — the monitor is still running.

| Launch shape | terminal state seen | never |
| --- | ---: | ---: |
| background shell (`run_in_background`) | 869 | 706 |
| Bash auto-backgrounded (`timedOutAfterMs` present) | 62 | 149 |
| Monitor (`taskId`) | 89 | 110 |
| **total** | **1020** | **965** |

**45% of launches never reach a terminal state in their transcript.** The
session ends, the task is torn down with no marker, or the notification
lands in a later session as an orphan summary.

## Lifetimes, for the tasks that do end

Launch to terminal notification: median 92 s, p90 1260 s, p95 3601 s,
p99 87572 s, max 104446 s. Launch to end of transcript, for the ones that
never end: median 3397 s, p25 883 s.

The two distributions overlap heavily, so **no age cutoff separates a live
task from an abandoned one.** A 30-minute bound would expire a live job at
p90 and still keep a dead one for half an hour.

## Why it matters

Any classifier that treats "launched and not yet terminal" as *waiting*
must bound that set. Carried across a whole transcript, one stale id holds
the verdict at `waiting` for the rest of the session: `worker-stop-alert.sh`
would never alert again, however silently the worker stopped — the failure
mode #820 exists to prevent, hidden behind a benign verdict (the shape
#859 already hit with teammate ids).

The bound `worker-stop-alert.sh` uses is the turn: only tasks launched since
the last turn start count. Its cost is the inverse error — a message
arriving mid-job restarts the turn, so that stop alerts while the job still
runs. A false alert costs a pane read; a suppressed one costs the signal.
#900 holds the question of a liveness-evidence bound (a poll of the task, a
monitor event since the turn start) that would cover both.

Filed from the #886 build, round-2 verification finding V1.
