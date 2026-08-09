---
name: sandcastle-watch
description: Run Sandcastle and watch it hands-off — a background watch loop digests the run log every ~90s via a throwaway subagent and reports progress on change, notifying you on the headline moments (issue done, PR opened, failure, run complete).
disable-model-invocation: true
---

# Run Sandcastle and watch it for me

Start a Sandcastle run and monitor it hands-off: report progress on change, notify on milestones, stay silent otherwise. The user should not have to look.

## 0. Preconditions
Repo must have `.sandcastle/main.mts` and a `sandcastle` npm script (`npm run | grep sandcastle`). Missing → stop: "No Sandcastle here — run `/setup-sandcastle` first."

Never start a second run against the same repo — concurrent label writes corrupt state. Check for a live one first, but match the run **process**, not a command-string: `pgrep -f 'sandcastle/main.mts'` also matches your own shell command (which contains that string), a false positive that makes it look like a run is live when none is. The real run is a `node` process; your shell is `bash`, so filter on that:

    pgrep -f 'main\.mts' | while read -r pid; do [ "$(ps -o comm= -p "$pid")" = node ] && echo "$pid"; done

If that prints a pid, a run is already going — you can't capture its stdout after the fact, so attach to the newest per-agent log (`.sandcastle/logs/<branch>-<name>.log`, e.g. `main-planner.log`) and skip to step 2, watching those instead of `$LOG`. Starting fresh in step 1 is preferred when you have the choice, since only a fresh launch captures the combined stdout stream.

**Done when:** preconditions pass and you know whether you're starting a run or attaching to a live one.

## 1. Start the run
Sandcastle's milestone markers — phase/iteration headers, work assignments, `✓/✗/⚠` outcomes, `→ PR #N`, the final `=== Run Summary ===` — all go to **stdout**. Do **not** rely on a live `.sandcastle/logs/run-*.log`: this orchestrator writes `run-<id>.log` only once at the very end (just the summary), and its startup pruner deletes any header-less log you drop into `.sandcastle/logs` (a hand-made boot log included). So capture npm's stdout yourself, to a durable path **outside** `.sandcastle/logs` where the pruner can't touch it, and watch that:

    LOG=$(mktemp /tmp/sandcastle-watch-XXXXXX.log)
    npm run sandcastle > "$LOG" 2>&1

Launch that with `run_in_background` so the harness tracks the npm process itself and notifies you when it exits. Remember `$LOG` — it is the live combined stream for the whole run, and reused by every tick in step 2. If the run dies at startup, `$LOG` holds the traceback.

**Done when:** the run is in the background (harness-tracked) and you have the `$LOG` path.

## 2. Watch loop (every ~90s until the run exits)
Sandcastle's per-milestone progress is not notified — only the final exit is — so sample `$LOG` on an interval. Track a byte offset into `$LOG` across ticks (starts at 0). Each tick:

1. Spawn a **fire-and-return subagent** (no name, foreground) with this job: "Read `$LOG` from byte offset `<N>` onward — the path and offset the main agent passes you; a fresh subagent keeps no state between ticks — plus the tail of the newest `.sandcastle/logs/<branch>-<name>.log`. Return a compact status: current phase/iteration, issues in flight and their state, PRs opened, new failures/warnings, whether the run has finished, and the new end-of-file offset." Digesting the verbose agent chatter is exactly the noisy work to keep off the main context.
2. Advance `<N>` to the offset it returned. Diff its status against the last one: if nothing changed, say nothing; if it changed, tell the user one or two lines — what moved.
3. Write a one-line digest to `.sandcastle/logs/watch-status` in the run's repo (e.g. `🏰 iter 2/5 · 3 PRs · 1✗`) — **every tick, even when nothing changed.** The scoped `sandcastle-segment.sh` ccstatusline segment (shipped alongside this skill in `sandcastle-watch/`; ccstatusline's `commandPath` points at it) shows this file only in the window whose cwd is that repo, and drops it once it's older than 180s, so re-writing each ~90s tick is what keeps the status-bar line alive.
4. On a **headline milestone** — iteration boundary, an issue done/failed, a PR opened, or the run finishing — also send the user a push notification. On WSL (`command -v powershell.exe`), fire a Windows desktop toast alongside it, so the milestone lands on the desktop the user is actually looking at:

       # if/fi, not &&: a bare && leaks exit 1 on every non-WSL machine.
       if command -v powershell.exe >/dev/null; then powershell.exe -NoProfile -ExecutionPolicy Bypass \
         -File "$(wslpath -w sandcastle-watch/toast.ps1)" -Title "sandcastle-watch" -Body "<milestone>"; fi

   Off WSL the guard skips it and the push notification is the only channel. `toast.ps1` escapes and strips its own arguments, so a milestone carrying `&` or ANSI colour is safe.
5. Reschedule the next check (~90s).

**Done when:** the background job has exited (proceed to step 3).

## 3. Finish
On exit, do one final digest, show Sandcastle's own `=== Run Summary ===` block as the closing report, send a final "run complete — N PRs, M failed" notification, delete `.sandcastle/logs/watch-status` so the status bar clears at once (the 180s freshness guard is only the backstop for a loop that dies uncleanly), and stop the loop.

## Markers the digest subagent keys off
`=== Phase 0 … ===` / `=== Reconciliation sweep … ===` / `=== Iteration N/MAX ===` · `  [mode] id: title → branch` (work in flight) · `  ✓` / `  ✗ id …` / `  ⚠ id …` (outcomes) · `… → PR #N` · the final `=== Run Summary ===` bucketed block.
