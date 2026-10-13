# job-wake live check in a herdr pane (2026-10-13)

Question (#1371, the job-wake mod of spec #1365): does the mod wake a real
session, in a herdr pane, when a `job-run` job the session started ends? And
does it see the job name `wrap-background-jobs.sh` gives a wrapped call?

## Answer

**Yes to both.** The mod's `classic.PreToolUse` hook reads the settings
hook's rewrite from `next(e)`, so it learns the wrapped job's name. Its
`$.prompt.submit` started a turn in an idle session in a herdr pane.

One thing the check showed that the ticket did not expect: a
`run_in_background` call also raises the harness's own completion notice, so
that job's end started **two** turns, the notice's and the mod's.

## What was run

Claude Code 2.1.296, WSL, one interactive session on Haiku in auto mode, in
a new herdr tab (`herdr tab create`, then `herdr pane run`), started with
`claude --plugin-dir <worktree>/flow/mods/job-wake --debug-file <log>`. The
debug log's load line: `hooks module job-wake@inline loaded (worker,
environment 1, tier user); events: session.start,classic.PreToolUse,tool.call`.

| Job | How it was started | What woke the session |
|---|---|---|
| `sleep 25` | `run_in_background: true`; the guard renamed it `sleep-3g7PSx7V` | the harness notice first, then the mod's prompt |
| `sh -c "sleep 20; echo Traceback demo; exit 3"` as `live1371` | a foreground call ending in `&`, so the harness tracked no task | the mod's prompt alone, within four seconds of the job's recorded end |

The pane, first job:

```
● STARTED
● Background command "Sleep 25 seconds in background" completed (exit code 0)
● The background sleep 25 finished with exit code 0. Nothing else is pending from it.
› Prompt from the job-wake plugin
❯ The job-wake plugin sent a message:
  job-wake: job sleep-3g7PSx7V: finished sleep-3g7PSx7V rc=0 cause=exit ended=2026-10-13T14:56:42Z
  progress: /home/caneff/.cache/agent-jobs/sleep-3g7PSx7V/progress
```

The pane, second job:

```
● DETACHED
› Prompt from the job-wake plugin
❯ The job-wake plugin sent a message:
  job-wake: job live1371: finished live1371 rc=3 cause=exit ended=2026-10-13T14:57:20Z
  matched line: 2026-10-13T14:57:20Z Traceback demo
  progress: /home/caneff/.cache/agent-jobs/live1371/progress
```

The debug log stamps that `$.prompt.submit` at `14:57:23.899Z`.

## Not covered

- A session parked on a permission dialog when the job ends.
- A session idle for hours; the longest wait here was 25 s.
- `claude -p` and SDK hosts.
- A failure line while the job is still running. The second job printed its
  line and exited within one poll, so the line arrived with the exit. The
  mid-run case is covered by the mod's tests only.
- A reload or a restart between the launch and the job's end. The mod keeps
  its watches in `$.store`; only its tests exercise picking them up.

## Cleanup

`/exit` ended the session and `herdr tab close` closed the tab. A process
listing afterwards showed no `claude --plugin-dir` process. The two job
directories under `~/.cache/agent-jobs/` are left for `job-run`'s 14-day
prune.
