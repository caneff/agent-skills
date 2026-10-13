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

## Second check, after the review round

The review wave found that reading the launch out of the command missed
ordinary spellings (`nohup`, a quoted or computed name, a path-qualified
`job-run`). The mod was rebuilt: `job-run` writes `$CLAUDE_CODE_SESSION_ID`
to the run directory's `session` file, and the mod watches the runs whose
file holds its own `$.session.id()`. The first check above ran the older
build. This one ran the rebuilt mod, in a new herdr tab whose `PATH` put the
worktree's `flow/bin` first, in manual permission mode.

**The two ids are the same value.** The run directory's `session` file read
`937b303e-a0f7-4333-891e-9a18ff26d15c`, and the mod found the run by its own
session id.

| Job | How it was started | What happened |
|---|---|---|
| `live2-1927686`: `sleep 8; echo Traceback demo; sleep 20; exit 3` | foreground, `nohup job-run --name "live2-$$" -- … &` | the Bash result carried `job-wake: watching live2-1927686`; one prompt on the failure line while it ran; one prompt on its end, with no matched line repeated |
| `sleep 12`, renamed `sleep-wk5X8D9r` by the guard | `run_in_background: true`, in a third session in auto mode | the Bash result carried `job-wake: watching sleep-wk5X8D9r`; the harness notice came first, then the mod's prompt with `finished sleep-wk5X8D9r rc=0` |
| `live2-dialog`: `sleep 6; exit 0` | the same form, followed at once by a second command that raised a permission dialog | the job ended while the session sat on the dialog; the mod's `$.prompt.submit` is stamped `15:20:03.862Z` in the debug log, the same second the job ended; the prompt ran as its own turn after the dialog was answered and the turn ended, once |

The pane, first job:

```
● The job launched with no error output. The only job-wake line in the tool context is:
  job-wake: watching live2-1927686; end the turn, and a prompt arrives when it ends or prints a failure line.
› Prompt from the job-wake plugin
❯ The job-wake plugin sent a message:
  job-wake: job live2-1927686: still running, and its output matched a failure signature
  matched line: 2026-10-13T15:19:23Z Traceback demo
  progress: /home/caneff/.cache/agent-jobs/live2-1927686/progress
› Prompt from the job-wake plugin
❯ job-wake: job live2-1927686: finished live2-1927686 rc=3 cause=exit ended=2026-10-13T15:19:43Z
  progress: /home/caneff/.cache/agent-jobs/live2-1927686/progress
```

Afterwards the `live2-*` run directories each held a `woken-end` file with
the run's pid, and the first a `woken-line` file as well.

One thing the dialog case showed: `$.prompt.submit` does not resolve until
its turn starts, so the mod's poll waits on it. While a wake is queued behind
a running turn, no other job of that session is polled. They are polled
again once the turn ends.

## Not covered

- A session idle for hours; the longest wait here was 25 s.
- `claude -p` and SDK hosts.
- A reload or a restart between the launch and the job's end. The mod
  rebuilds its list from the run directories; only its tests exercise that.
- Whether a resumed session keeps its session id. If it does not, the
  resumed session does not find the runs the earlier one started.

## Cleanup

`/exit` ended each session and `herdr tab close` closed each tab. A process
listing afterwards showed no `claude --plugin-dir` process. The five job
directories under `~/.cache/agent-jobs/` are left for `job-run`'s 14-day
prune.
