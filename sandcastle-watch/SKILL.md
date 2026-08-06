---
name: sandcastle-watch
description: Run Sandcastle and watch it hands-off — a background watch loop digests the run log every ~90s via a throwaway subagent and reports progress on change, notifying you on the headline moments (issue done, PR opened, failure, run complete).
disable-model-invocation: true
---

# Run Sandcastle and watch it for me

Start a Sandcastle run and monitor it hands-off: report progress on change, notify on milestones, stay silent otherwise. The user should not have to look.

## 0. Preconditions
Repo must have `.sandcastle/main.mts` and a `sandcastle` npm script (`npm run | grep sandcastle`). Missing → stop: "No Sandcastle here — run `/setup-sandcastle` first."

Never start a second run against the same repo — concurrent label writes corrupt state. Check for a live one first: `pgrep -f 'sandcastle/main.mts'`. If it returns a pid, a run is already going — attach to the newest `.sandcastle/logs/run-*.log` and skip to step 2 instead of starting another.

**Done when:** preconditions pass and you know whether you're starting a run or attaching to a live one.

## 1. Start the run
Make sure the log dir exists, then launch in the background, redirecting combined output to a fresh timestamped run log. Keep the job handle — the harness notifies you when it exits:

    mkdir -p .sandcastle/logs
    npm run sandcastle > .sandcastle/logs/run-$(date +%s).log 2>&1 &

**Done when:** the background job is running and you have its run-log path.

## 2. Watch loop (every ~90s until the run exits)
Sandcastle's per-milestone progress is not notified — only the final exit is — so sample the run log on an interval. Track a byte offset into the run log across ticks (starts at 0). Each tick:

1. Spawn a **fire-and-return subagent** (no name, foreground) with this job: "Read `<run-log>` from byte offset `<N>` onward — the offset the main agent passes you; a fresh subagent keeps no state between ticks — plus the tail of the newest `.sandcastle/logs/<branch>-<name>.log`. Return a compact status: current phase/iteration, issues in flight and their state, PRs opened, new failures/warnings, whether the run has finished, and the new end-of-file offset." Digesting the verbose agent chatter is exactly the noisy work to keep off the main context.
2. Advance `<N>` to the offset it returned. Diff its status against the last one: if nothing changed, say nothing; if it changed, tell the user one or two lines — what moved.
3. On a **headline milestone** — iteration boundary, an issue done/failed, a PR opened, or the run finishing — also send the user a push notification.
4. Reschedule the next check (~90s).

**Done when:** the background job has exited (proceed to step 3).

## 3. Finish
On exit, do one final digest, show Sandcastle's own `=== Run Summary ===` block as the closing report, send a final "run complete — N PRs, M failed" notification, and stop the loop.

## Markers the digest subagent keys off
`=== Phase 0 … ===` / `=== Reconciliation sweep … ===` / `=== Iteration N/MAX ===` · `  [mode] id: title → branch` (work in flight) · `  ✓` / `  ✗ id …` / `  ⚠ id …` (outcomes) · `… → PR #N` · the final `=== Run Summary ===` bucketed block.
