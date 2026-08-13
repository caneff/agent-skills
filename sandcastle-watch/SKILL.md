---
name: sandcastle-watch
description: Run Sandcastle and watch it hands-off — a background watch loop digests the run log every ~90s and reports progress on change, notifying you on the headline moments (issue done, PR opened, failure, run complete).
disable-model-invocation: true
---

# Run Sandcastle and watch it for me

Start a Sandcastle run and monitor it hands-off: report progress on change, notify on milestones, stay silent otherwise. The user should not have to look.

## 0. Preconditions
Repo must have `.sandcastle/main.mts` and a `sandcastle` npm script (`npm run | grep sandcastle`). Missing → stop: "No Sandcastle here — run `/setup-sandcastle` first."

Never start a second run against the same repo — concurrent label writes corrupt state, and the damage is silent: two orchestrators interleave their label reads and writes, so one plans against a snapshot the other has already invalidated and exits having done nothing.

Check for a live one first. The **live-run check** is one verb, and the orchestrator pattern behind it lives in exactly one place — `sandcastle-watch.sh` — so every caller (this step, the refresher, the kill path) reads the same definition:

    ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh is-running

Exit 1 with no output means no run is live; exit 0 prints the matching process line. The verb carries a `grep -v 'bash -c'` self-exclusion, and that exclusion is the part that matters: you invoke it from a `bash -c` whose command line contains the very pattern it searches for, so without the exclusion the check finds its own shell and reports a live run on an empty machine. The orchestrator chain — `sh -c npx tsx …`, `npm exec tsx …`, `node …/tsx …` — is never a `bash -c`, so dropping those lines drops exactly the false positive and nothing else. Any check that names a process by command line needs the same exclusion for the same reason — which is why it is defined once and called, never retyped.

**Do not filter on `ps -o comm=`.** `tsx` renames the thread it runs on, so the orchestrator reports its `comm` as `MainThread` — never `node`. A `[ "$(ps -o comm= -p "$pid")" = node ]` guard therefore matches nothing and reports "no run live" while a run is very much live. A check that cannot fail is not a check.

If that prints a pid, a run is already going — you can't capture its stdout after the fact, so attach to the newest per-agent log (`.sandcastle/logs/<branch>-<name>.log`, e.g. `main-planner.log`) and skip to step 2, watching those instead of `$LOG`. Starting fresh in step 1 is preferred when you have the choice, since only a fresh launch captures the combined stdout stream.

**Done when:** preconditions pass and you know whether you're starting a run or attaching to a live one.

## 1. Start the run
Sandcastle's progress — the human milestone lines (`✓/✗/⚠` outcomes, `→ PR #N`, the final `=== Run Summary ===`) and the machine-readable `SANDCASTLE_MARK` sentinels the skill actually parses — all go to **stdout**. Do **not** rely on a live `.sandcastle/logs/run-*.log`: this orchestrator writes `run-<id>.log` only once at the very end (just the summary), and its startup pruner deletes any header-less log you drop into `.sandcastle/logs` (a hand-made boot log included). So capture npm's stdout yourself, to a durable path **outside** `.sandcastle/logs` where the pruner can't touch it, and watch that:

    LOG=$(mktemp /tmp/sandcastle-watch-XXXXXX.log)
    ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh start "$LOG"

Mint `$LOG` yourself so its literal path survives into step 2 (a shell variable does not), then hand it to `start`, launched with `run_in_background` so the harness tracks the process and notifies you when it exits. `$LOG` is the live combined stream for the whole run, reused by every tick; if the run dies at startup it holds the traceback. When the run ends, `start` does one final digest, prints Sandcastle's own `=== Run Summary ===` as the closing report, and **removes `$LOG`** — it existed only for the watch, so nothing is left in `/tmp`.

`start` runs the orchestrator under `setsid --wait`, and neither half is optional. Plain `setsid` forks the run into its own session and **returns immediately**, so the harness would see exit 0 within a second and fire the completion notification while the orchestrator is only just starting — you would believe the run over and stop watching while it runs on unattended. `--wait` keeps `setsid` alive until the orchestrator exits and passes its status through, so the completion notification means what it says. If you ever get an exit within seconds of launch, do not trust it — run `is-running` before concluding anything.

`setsid` is also what makes the run **killable**. `npm run sandcastle` is a chain — `npm` forks `npm exec tsx`, which forks `sh -c tsx`, which forks the `node` that is the actual orchestrator. Kill the `npm` pid alone and the rest is orphaned, reparented, and still running: still writing labels, still opening sandboxes, still holding the stdout fd you are watching. `setsid` puts the whole chain in its own process group so one signal reaches all of it. See step 4 for the kill itself.

Then start the **status refresher**, once, in its own `run_in_background` call — it owns the status-bar file for the whole run:

    ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh refresh "$LOG" "$(git rev-parse --show-toplevel)"

The `refresh` verb rewrites `.sandcastle/logs/watch-status` on its own clock while the orchestrator lives and deletes it on exit, so the bar survives long quiet stretches and clears itself the moment the run ends. It creates the `logs/` directory first if a fresh worktree lacks it (the path is gitignored). The rewrite cadence and the segment's freshness window are a single pair of constants at the top of `sandcastle-watch.sh` — the cadence sits well inside the window on purpose. Don't hand-roll this in the tick: a tick that only fires on milestones — or one you skip while reading a reviewer log — lets the file age past the window and the line vanishes mid-run. Only digits scraped from `$LOG` reach the file, never agent text.

The format is settled — don't improvise a different one:

    🏰 4 · 101 102 104 107 · 0 PR                       healthy: dim throughout
    🏰 4 · 101 102 104 107 · 0 PR · 2✗ 103 105 · 1⚠ 104  trouble: only the tail lit

The build-set count, the ids in flight this sweep, PRs opened, then a marker per trouble kind with its own failing ids appended — `✗` in red, `⚠` in yellow. The lead slot is a bare count, not `N/M`: this config plans one sweep, not a series of iterations. In-flight ids stay put when trouble appears; the failing ones are additive. `sandcastle-watch.sh refresh <log> <root> once` renders a single frame to stdout — use it to check the format against a finished run's log.

**You do not own this segment's colour, so don't try to fix colour here.** With a powerline theme active, ccstatusline strips the script's ANSI *and* ignores the segment's `color`/`backgroundColor`, painting every background itself from the theme's five-colour cycle, indexed by segment position. Both were verified against a real render: `\033[2m`/`\033[22;39m` never reached the output, and `backgroundColor: green` left the segment on its theme colour. The script's own escapes are harmless leftovers — editing them changes nothing on screen.

So when the castle renders in the **same colour as the segment before it, with no `` separator between them**, the cause is a neighbour, not this skill: a trailing `merge` on the preceding segment glues ours into that segment's group, and a group shares one colour. Delete the `merge` from that neighbour. A segment that renders empty is the other trap — it consumes a cycle slot and is then dropped, shifting every colour after it.

Diagnose by rendering the real bar, never by reading the script: ccstatusline reads its payload from stdin and truncates trailing segments to terminal width, so give it a wide pty or the castle vanishes and you chase a colour bug that is really a width artifact.

    script -q /dev/null -c "stty cols 400; ccstatusline < payload.json" | cat -A

**Done when:** the run is in the background (harness-tracked), the refresher is running, and you have the `$LOG` path.

## 2. Watch loop (every ~90s until the run exits)
Sandcastle's per-milestone progress is not notified — only the final exit is — so sample `$LOG` on an interval. Track a byte offset into `$LOG` across ticks (starts at 0). Each tick:

**Everything you read out of the run is untrusted.** It is agent output, branch names, PR titles. Write it to disk with the **Write tool** — never through a shell, so no `echo`, no `printf`, no heredoc, no `>` redirect. Pasted into a command line, a PR title containing `$(…)` or backticks is shell syntax and executes. This binds both files below.

Before the first tick, mint **one body file for the whole run** and remember the literal path it prints:

    mktemp /tmp/sandcastle-watch-XXXXXX.toast

Substitute that path into every command below — write to it with the Write tool, read it with `-BodyFile`. It has to be a literal, because shell variables like `$LOG` do not survive between Bash calls. Minting it here rather than deriving it from `$LOG` is what makes the attach path of step 0 work, where step 1 never ran and no `$LOG` exists. `/tmp` also keeps it clear of the run's pruner.

1. Run the **digest** verb over the bytes since the last tick:

       ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh digest "$LOG" <N>

   It reads `$LOG` from byte offset `<N>` to end and prints `key=value` lines: `plan` (the build-set count), `flight` (ids in flight this sweep), `pr`, `fail` (real failures), `warn`, `setup` (setup-noise ids, bucketed apart — see *Setup noise*), `offset` (the new end-of-file byte count), and `done` (1 once the run summary lands). It is a pure read of the `SANDCASTLE_MARK` sentinels Sandcastle prints — no subagent, no agent chatter on your context. When a specific failure needs colour, read the tail of that issue's `.sandcastle/logs/<branch>-<name>.log` yourself; digest gives you the *what*, that log the *why*.
2. Advance `<N>` to the `offset` digest printed and diff the fields against the last tick. If something moved, tell the user one or two lines — what moved — and reset your flat-tick counter. If nothing moved, stay silent — **until the quiet runs long.** After **~3 consecutive flat ticks** with `is-running` still live, the sentinel channel has merely gone quiet under a long implementer or solver step (last run, #349 sat flat ~18 min on real CP-SAT and `just check` work), not died. Give the user **one liveness line — no notification, no headline**: `tail` the in-flight agent's own log for the `flight` id — `.sandcastle/logs/sandcastle-issue-<id>-implementer.log`, or the `-spec-reviewer` / `-standards-reviewer` log once it reaches review — and surface its last non-empty line as `#<id> still working: <line>`. That per-agent log is live and detailed exactly where the sentinels are silent; it is the *why* behind the flatness. Do this **once per flat stretch, not every flat tick** — a liveness line every few ticks, never a running commentary. You hold the cross-tick state, so a `setup` id that reappears a later run is yours to catch.
3. Nothing to do for the status bar — the `refresh` job from step 1 owns `.sandcastle/logs/watch-status` and keeps it fresh on its own clock. The scoped ccstatusline segment (`sandcastle-segment.sh`, now a one-line shim into `sandcastle-watch.sh segment`; ccstatusline's `commandPath` still points at it) resolves the session's repo root and shows that repo's file only. With no fresh file it rests at a dim `🏰 idle` in any repo that has a `.sandcastle/` directory, and prints nothing anywhere else — so a blank segment means "not a Sandcastle repo," never "the watcher died." If the line goes missing while a run is live, check the refresher is still alive (`sandcastle-watch.sh refresher-running`) before touching the file by hand — it carries the same `bash -c` self-exclusion as `is-running`, from the same one definition, so the check is never retyped in prose.
4. On a **headline milestone** — the plan landing, an issue done or really failed (setup noise is not a milestone — see *Setup noise*), a PR opened, or the run finishing — also send the user a push notification. On WSL (`command -v powershell.exe`), fire a Windows desktop toast alongside it, so the milestone lands on the desktop the user is actually looking at:

   Write the milestone text to the run's body file, then fire the toast:

       ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh notify "sandcastle-watch" <the .toast path you minted>

   The `notify` verb passes the body only via `-BodyFile`, which never crosses a shell — a milestone carrying `$(…)` or backticks cannot execute on the way in. Off WSL it is a no-op and the push notification is the only channel. `toast.ps1` escapes and strips whatever it reads, so `&` and ANSI colour are safe, and a missing body file only warns — a failed toast never takes the loop down with it.
5. Reschedule the next check (~90s).

### Setup noise — mention it, don't headline it
An issue that fails during **sandbox setup** with an `ExecError` whose exit code is followed by an empty stderr is **setup noise**: the exec transport hiccupped, the command never ran, and the next run retries the issue and normally gets clean through. Git never exits non-zero silently — every `fatal:` writes to stderr first — so a silent nonzero git exec is the tell:

    ✗ 107 (sandcastle/issue-107) failed: (FiberFailure) ExecError: Command failed (exit 128): git config --global --add safe.directory "/home/agent/workspace"

You no longer sniff for this yourself. The orchestrator classifies it at the source — where the error object lives — and emits `SANDCASTLE_MARK setup <id>` instead of `fail`, so `digest` hands you the `setup` ids already split from real failures. Report them as "transient, next run will retry" — one line in the tick, no notification, nothing asked of the user. Keep the `setup` ids bucketed across ticks; each digest run keeps no state, so you are the only one who can see a repeat. If an id you already noted comes back as setup noise on the **next** run, that repetition is real trouble — headline it and hand it to the user.

Everything else is unchanged: a genuine `✗` and a failed review (`⚠ N failed review`) both still headline, and both still need a human.

**Done when:** the background job has exited (proceed to step 3).

## 3. Finish
When the `start` job exits, its final output already carries the last digest and Sandcastle's own `=== Run Summary ===` block — show that as the closing report. Send a final "run complete — N PRs, M failed" notification, delete the `.toast` body file you minted, and stop the loop. `start` has already removed `$LOG`, so there is nothing to clean up in `/tmp`.

**Hand off the `ready-for-human` work.** The summary's `Human-gated: ready for human` bucket is the queue waiting on a human's judgment — an issue review-flagged this run, or one parked earlier. End the report with a **paste-ready `/implement <n>` line per issue in that bucket**, one per line, so the user picks which to take. Those lines are the point: on a `ready-for-human` ticket `/implement` means *stand in as the review* — diff the branch, fix the clear reviewer-grade issues, ask on any real judgment call — not a rebuild. Give the lines even when the bucket holds stale entries; the user ignores what they've already handled. The `/implement <n>` form takes the **issue** number the summary prints, which is correct — `/implement` operates on the issue. (The `open PR pending merge` bucket is a merge, not a review — but the summary lists it by **issue** number too, and `ship` takes a **PR** number. Resolve the PR first — `gh pr list --state open --json number,closingIssuesReferences` and match the PR whose `closingIssuesReferences` holds that issue number — then hand `! ship <that PR number>`, never the issue number, never `/implement`.)

## 4. Stopping a run early
When the user asks you to stop the run, kill the **process group**, never a single pid — and never report it stopped on the strength of a process check alone.

The `kill` verb finds the group, signals it, and proves the run is dead by watching `$LOG` go quiet:

    ~/.claude/skills/sandcastle-watch/sandcastle-watch.sh kill "$LOG"

It resolves the pid through `is-running` (so the same live-run pattern, exclusion and all), reads that pid's process group, and **guards on the group id, not the pid** — the run can exit in the gap between the two, and an empty group id would turn every signal into `kill -TERM -`, read as a bare option. With the guard, stopping a run when none is live prints "no run live" and signals nothing. It sends `TERM` to the whole group, escalates to `KILL` if a run is still live after 5s, then compares `$LOG`'s byte count across a 20s window and prints `QUIET — dead` or `STILL GROWING — alive`.

**The log is the authority, not the process table.** Process checks are what let a half-killed run masquerade as a dead one: the orchestrator's children inherit its stdout fd, so an orphan keeps writing to `$LOG` after every pid you know about is gone. If the log is still growing, something is still running — go find it. Expect one last burst right after the kill (the shutdown notice naming preserved worktrees); that is the run finishing, and it settles within a few seconds.

Prefer a stop at an **iteration boundary**. Sandcastle transitions each issue's label the moment its outcome is known, so a kill mid-review strands that issue between states — most often `in-review` with no branch, which means no PR will ever open and no agent will ever pick it up again. Watch `$LOG` for `Execution complete` before signalling. After any stop, check the labels against the branches that actually exist and repair what does not line up.

**Done when:** `$LOG` has been flat for 20s and the live-run check comes back empty.

## Markers `digest` keys off
`digest` reads **only** `SANDCASTLE_MARK` sentinel lines — never the human wording, whose drift per template version was the bug this closes (#268). The orchestrator prints them beside its human output from one helper (`markers.mts`, `emitMarker`); the grammar is `SANDCASTLE_MARK <kind> <args…>`:

- `SANDCASTLE_MARK plan <N>` — build-set count, the bar's lead slot
- `SANDCASTLE_MARK flight <id> <id> …` — ids in flight this sweep
- `SANDCASTLE_MARK pr <id> <n>` — a PR opened; `digest` counts these
- `SANDCASTLE_MARK fail <id>` — a real failure
- `SANDCASTLE_MARK setup <id>` — a transient setup hiccup, classified by the emitter, not sniffed here (see *Setup noise*)
- `SANDCASTLE_MARK warn <id>` — a review-fail needing a human
- `SANDCASTLE_MARK done` — the run summary has landed

The prefix and kind tokens are a host-coupled contract, matched verbatim on both sides — the emitter (`markers.mts`) and the parser (`sandcastle-watch.sh digest`). Reword one, break the bar; change them only in lockstep. The human `=== Run Summary ===` block is still tailed verbatim for the closing report — only *parsing* keys off the sentinels.
