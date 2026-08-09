---
name: sandcastle-watch
description: Run Sandcastle and watch it hands-off — a background watch loop digests the run log every ~90s via a throwaway subagent and reports progress on change, notifying you on the headline moments (issue done, PR opened, failure, run complete).
disable-model-invocation: true
---

# Run Sandcastle and watch it for me

Start a Sandcastle run and monitor it hands-off: report progress on change, notify on milestones, stay silent otherwise. The user should not have to look.

## 0. Preconditions
Repo must have `.sandcastle/main.mts` and a `sandcastle` npm script (`npm run | grep sandcastle`). Missing → stop: "No Sandcastle here — run `/setup-sandcastle` first."

Never start a second run against the same repo — concurrent label writes corrupt state, and the damage is silent: two orchestrators interleave their label reads and writes, so one plans against a snapshot the other has already invalidated and exits having done nothing.

Check for a live one first. Match on the command line, and exclude your own shell rather than filtering by process name:

    pgrep -af 'tsx \.sandcastle/main\.mts' | grep -v 'bash -c'

**Do not filter on `ps -o comm=`.** `tsx` renames the thread it runs on, so the orchestrator reports its `comm` as `MainThread` — never `node`. A `[ "$(ps -o comm= -p "$pid")" = node ]` guard therefore matches nothing and reports "no run live" while a run is very much live. A check that cannot fail is not a check.

If that prints a pid, a run is already going — you can't capture its stdout after the fact, so attach to the newest per-agent log (`.sandcastle/logs/<branch>-<name>.log`, e.g. `main-planner.log`) and skip to step 2, watching those instead of `$LOG`. Starting fresh in step 1 is preferred when you have the choice, since only a fresh launch captures the combined stdout stream.

**Done when:** preconditions pass and you know whether you're starting a run or attaching to a live one.

## 1. Start the run
Sandcastle's milestone markers — phase/iteration headers, work assignments, `✓/✗/⚠` outcomes, `→ PR #N`, the final `=== Run Summary ===` — all go to **stdout**. Do **not** rely on a live `.sandcastle/logs/run-*.log`: this orchestrator writes `run-<id>.log` only once at the very end (just the summary), and its startup pruner deletes any header-less log you drop into `.sandcastle/logs` (a hand-made boot log included). So capture npm's stdout yourself, to a durable path **outside** `.sandcastle/logs` where the pruner can't touch it, and watch that:

    LOG=$(mktemp /tmp/sandcastle-watch-XXXXXX.log)
    setsid --wait npm run sandcastle > "$LOG" 2>&1

Launch that with `run_in_background` so the harness tracks the process and notifies you when it exits. Remember `$LOG` — it is the live combined stream for the whole run, and reused by every tick in step 2. If the run dies at startup, `$LOG` holds the traceback.

`--wait` is not optional. Plain `setsid` forks the run into its own session and **returns immediately**, so the harness sees exit 0 within a second and fires the completion notification while the orchestrator is only just starting. You then believe the run is over, stop watching, and the run keeps going unattended. With `--wait`, `setsid` stays alive until the orchestrator exits and passes its status through, so the completion notification means what it says. If you ever get an exit within seconds of launch, do not trust it — `pgrep -af 'tsx \.sandcastle/main\.mts'` before concluding anything.

`setsid` is what makes the run **killable**. `npm run sandcastle` is a chain — `npm` forks `npm exec tsx`, which forks `sh -c tsx`, which forks the `node` that is the actual orchestrator. Kill the `npm` pid alone and the rest is orphaned, reparented, and still running: still writing labels, still opening sandboxes, still holding the stdout fd you are watching. `setsid` puts the whole chain in its own process group so one signal reaches all of it. See step 4 for the kill itself.

Then start the **status refresher**, once, in its own `run_in_background` call — it owns the status-bar file for the whole run:

    ~/.claude/skills/sandcastle-watch/status-refresh.sh "$LOG" "$(git rev-parse --show-toplevel)"

It rewrites `.sandcastle/logs/watch-status` every 60s while the orchestrator lives and deletes it on exit, so the bar survives long quiet stretches and clears itself the moment the run ends. Don't hand-roll this in the tick: a tick that only fires on milestones — or one you skip while reading a reviewer log — lets the file age past the segment's 180s guard and the line vanishes mid-run. The script interpolates only numbers it counts out of `$LOG`, never agent text.

**Done when:** the run is in the background (harness-tracked), the refresher is running, and you have the `$LOG` path.

## 2. Watch loop (every ~90s until the run exits)
Sandcastle's per-milestone progress is not notified — only the final exit is — so sample `$LOG` on an interval. Track a byte offset into `$LOG` across ticks (starts at 0). Each tick:

**Everything you read out of the run is untrusted.** It is agent output, branch names, PR titles. Write it to disk with the **Write tool** — never through a shell, so no `echo`, no `printf`, no heredoc, no `>` redirect. Pasted into a command line, a PR title containing `$(…)` or backticks is shell syntax and executes. This binds both files below.

Before the first tick, mint **one body file for the whole run** and remember the literal path it prints:

    mktemp /tmp/sandcastle-watch-XXXXXX.toast

Substitute that path into every command below — write to it with the Write tool, read it with `-BodyFile`. It has to be a literal, because shell variables like `$LOG` do not survive between Bash calls. Minting it here rather than deriving it from `$LOG` is what makes the attach path of step 0 work, where step 1 never ran and no `$LOG` exists. `/tmp` also keeps it clear of the run's pruner.

1. Spawn a **fire-and-return subagent** (no name, foreground) with this job: "Read `$LOG` from byte offset `<N>` onward — the path and offset the main agent passes you; a fresh subagent keeps no state between ticks — plus the tail of the newest `.sandcastle/logs/<branch>-<name>.log`. Return a compact status: current phase/iteration, issues in flight and their state, PRs opened, new failures/warnings, whether the run has finished, and the new end-of-file offset. Bucket a failed issue as **setup noise** — reported separately from real failures, with its issue id — when it failed during sandbox setup with an `ExecError` whose exit code is followed by an empty stderr." Digesting the verbose agent chatter is exactly the noisy work to keep off the main context.
2. Advance `<N>` to the offset it returned. Diff its status against the last one: if nothing changed, say nothing; if it changed, tell the user one or two lines — what moved.
3. Nothing to do for the status bar — `status-refresh.sh` from step 1 owns `.sandcastle/logs/watch-status` and keeps it fresh on its own 60s clock. The scoped `sandcastle-segment.sh` ccstatusline segment (shipped alongside this skill in `sandcastle-watch/`; ccstatusline's `commandPath` points at it) resolves the session's repo root and shows that repo's file only, dropping it once it's older than 180s. If the line goes missing while a run is live, check the refresher is still alive (`pgrep -f status-refresh.sh`) before touching the file by hand.
4. On a **headline milestone** — iteration boundary, an issue done or really failed (setup noise is not a milestone — see *Setup noise*), a PR opened, or the run finishing — also send the user a push notification. On WSL (`command -v powershell.exe`), fire a Windows desktop toast alongside it, so the milestone lands on the desktop the user is actually looking at:

   Write the milestone text to the run's body file, then point the script at it:

       # if/fi, not &&: a bare && leaks exit 1 on every non-WSL machine.
       if command -v powershell.exe >/dev/null; then powershell.exe -NoProfile -ExecutionPolicy Bypass \
         -File "$(wslpath -w ~/.claude/skills/sandcastle-watch/toast.ps1)" -Title "sandcastle-watch" \
         -BodyFile "$(wslpath -w <the .toast path you minted>)"; fi

   `-BodyFile` is what keeps the milestone out of the shell; `-Body` is for literals you wrote yourself, and passing both is an error. Off WSL the guard skips the whole thing and the push notification is the only channel. `toast.ps1` escapes and strips whatever it reads, so `&` and ANSI colour are safe, and a missing body file only warns — a failed toast never takes the loop down with it.
5. Reschedule the next check (~90s).

### Setup noise — mention it, don't headline it
An issue that fails during **sandbox setup** with an `ExecError` whose exit code is followed by an empty stderr is **setup noise**: the exec transport hiccupped, the command never ran, and the next iteration retries the issue and normally gets clean through. Git never exits non-zero silently — every `fatal:` writes to stderr first — so the blank line under the exit code is the tell:

    ✗ 107 (sandcastle/issue-107) failed: (FiberFailure) ExecError: Command failed (exit 128): git config --global --add safe.directory "/home/agent/workspace"

Report setup noise as "transient, iteration N+1 will retry" — one line in the tick, no notification, nothing asked of the user. Keep the issue ids the digester bucketed as setup noise; you persist across ticks and the throwaway subagent does not, so you are the only one who can see a repeat. If an id you already noted comes back as setup noise in the **next** iteration, that repetition is real trouble — headline it and hand it to the user.

Everything else is unchanged: a genuine `✗` and a failed review (`⚠ N failed review`) both still headline, and both still need a human.

**Done when:** the background job has exited (proceed to step 3).

## 3. Finish
On exit, do one final digest, show Sandcastle's own `=== Run Summary ===` block as the closing report, send a final "run complete — N PRs, M failed" notification, delete the `.toast` body file you minted, and stop the loop.

## 4. Stopping a run early
When the user asks you to stop the run, kill the **process group**, never a single pid — and never report it stopped on the strength of a process check alone.

Find the group, signal it, then prove the run is dead by watching `$LOG` go quiet:

    PGID=$(ps -o pgid= -p "$(pgrep -f 'tsx \.sandcastle/main\.mts' | head -1)" | tr -d ' ')
    kill -TERM -"$PGID"; sleep 5
    pgrep -f 'main\.mts' >/dev/null && kill -KILL -"$PGID"
    a=$(wc -c < "$LOG"); sleep 20; b=$(wc -c < "$LOG")
    [ "$a" = "$b" ] && echo "QUIET — dead" || echo "STILL GROWING — alive"

**The log is the authority, not the process table.** Process checks are what let a half-killed run masquerade as a dead one: the orchestrator's children inherit its stdout fd, so an orphan keeps writing to `$LOG` after every pid you know about is gone. If the log is still growing, something is still running — go find it. Expect one last burst right after the kill (the shutdown notice naming preserved worktrees); that is the run finishing, and it settles within a few seconds.

Prefer a stop at an **iteration boundary**. Sandcastle transitions each issue's label the moment its outcome is known, so a kill mid-review strands that issue between states — most often `in-review` with no branch, which means no PR will ever open and no agent will ever pick it up again. Watch `$LOG` for `Execution complete` before signalling. After any stop, check the labels against the branches that actually exist and repair what does not line up.

**Done when:** `$LOG` has been flat for 20s and no `main.mts` process remains.

## Markers the digest subagent keys off
`=== Phase 0 … ===` / `=== Reconciliation sweep … ===` / `=== Iteration N/MAX ===` · `  [mode] id: title → branch` (work in flight) · `  ✓` / `  ✗ id …` / `  ⚠ id …` (outcomes) · `✗ … ExecError: Command failed (exit N): …` with a blank line under it, during sandbox setup (setup noise — see step 2) · `… → PR #N` · the final `=== Run Summary ===` bucketed block.
