# The lost-wake path: Claude Code's PTY-host orphan watchdog

Diagnosis for [#597](https://github.com/caneff/agent-skills/issues/597).
Reproduced 2026-09-07 against Claude Code `2.1.263` on WSL2.

## Verdict

Background jobs are killed by Claude Code's own PTY-host orphan watchdog, which
decides purely from *process topology* and never looks at whether the job is
healthy. When it fires, the process that would have delivered the completion
wake is the same one whose absence triggered the kill — so the job dies and
nothing wakes.

`#597`'s claim that these are "runtime events with no artifact to check" is
wrong for background *agent* jobs, and right for plain background Bash.

## Mechanism

From the shipped bundle (`~/.local/share/claude/versions/2.1.263`), the
`--bg-pty-host` process runs two timers:

- **Heartbeat** — `CLAUDE_PTY_HEARTBEAT_MS`, default `60000`. Three missed
  pings and the client socket is destroyed and removed from the live-client
  set `p`. There is no reconnect path back into `p`.
- **Orphan watchdog** — `CLAUDE_PTY_ORPHAN_CHECK_MS`, default `2000`, times
  `30` consecutive strikes, so **60 seconds**.

The watchdog's whole condition is:

```js
if (process.ppid === O || p.size > 0) { R = 0; return; }  // O = ppid at startup
if (++R < u) return;
Ff("ptyhost_orphan_watchdog");
d.kill("SIGTERM");  setTimeout(() => d.kill("SIGKILL"), 5000)
```

A kill therefore needs both **ppid changed** and **zero connected clients**.
In normal operation the Claude CLI is both the parent and the only client, so
a CLI that dies *or merely stalls long enough to miss three pings* satisfies
both arms at once. Under memory pressure that is one event, which is why
multiple jobs die in the same second.

The job's own liveness is never an input. A job printing output every 500ms is
killed exactly as fast as a hung one.

## Evidence on disk

`~/.claude/jobs/<id>/exit-cause`:

| job | exit-cause | written | state.json |
|---|---|---|---|
| `1f43db02` | `ptyhost_orphan_watchdog` | 2026-09-02 18:40:05 | `done` (twitch-rules-scroller e2e) |
| `370096f1` | `ptyhost_orphan_watchdog` | 2026-09-02 18:40:05 | `done` (fleet-rail) |

Same second, two jobs — one client stall drops every socket it holds.

`Ff` writes `exit-cause` only into `$CLAUDE_JOB_DIR`, which is set for
background *agent* jobs. A plain `run_in_background` Bash job killed the same
way **writes nothing**. That is the silent class: #243, #274, `9x9_28g`.

Ruled out: the Linux OOM killer. `dmesg -T` is readable on this box and holds
no OOM or `killed process` entries.

## Reproduction

Deterministic, ~16s, no Claude session involved — it drives the pty host
directly. 3/3 red on the orphan arm, green on both controls.

```bash
#!/usr/bin/env bash
# loop.sh <orphan_check_ms> [kill|nokill]
set -u
CLI=/home/caneff/.local/share/claude/versions/2.1.263
MS="${1:-200}"; MODE="${2:-kill}"
RUN=$(mktemp -d /tmp/wake-XXXXXX); SOCK="$RUN/pty.sock"

cat > "$RUN/job.sh" <<'JOB'
#!/usr/bin/env bash
P="$1"
for i in $(seq 1 80); do echo "$(date +%s.%N) step $i" >> "$P"; sleep 0.5; done
echo "JOB-COMPLETE" >> "$P"
JOB
chmod +x "$RUN/job.sh"

# P1 stays alive as the pty host's real parent (no exec -> genuine parent/child).
setsid bash -c "
  CLAUDE_PTY_ORPHAN_CHECK_MS=$MS CLAUDE_JOB_DIR=$RUN \
  '$CLI' --bg-pty-host '$SOCK' 80 24 -- '$RUN/job.sh' '$RUN/progress' &
  wait
" >/dev/null 2>"$RUN/ptyhost.err" &
P1=$!
sleep 3
HOST=$(pgrep -P "$P1" | head -1)
[ "$MODE" = "kill" ] && { kill -9 "$P1" 2>/dev/null; sleep 1; }

sleep 12
LAST=$(tail -1 "$RUN/progress" 2>/dev/null || echo "(none)")
ALIVE=$(pgrep -f "$RUN/job[.]sh" >/dev/null && echo yes || echo no)
echo "job_alive=$ALIVE exit_cause=$(cat "$RUN/exit-cause" 2>/dev/null || echo none)"
[ "$ALIVE" = no ] && [ "$LAST" != "JOB-COMPLETE" ] && echo "RED" || echo "GREEN"
kill -9 "$P1" "$HOST" 2>/dev/null; pkill -f "$RUN/job[.]sh" 2>/dev/null; true
```

| arm | command | result |
|---|---|---|
| orphaned (x3) | `./loop.sh 200 kill` | **RED** — killed at ~18/80 steps, `exit-cause=ptyhost_orphan_watchdog` |
| parent alive | `./loop.sh 200 nokill` | GREEN — `ppid` never changes, counter resets |
| grace raised | `./loop.sh 20000 kill` | GREEN — orphaned, but 10min grace outlives the job |

Two harness traps worth keeping, both of which produced false greens:

- `setsid` on the pty host itself makes `ppid == O == 1` from birth, so
  `process.ppid === O` holds forever and the watchdog never fires.
- `exec`ing the CLI from the parent shell collapses parent into host, so
  killing "the parent" kills the host instead. The job then *outlives* the
  host, which looks green for the wrong reason.

## Mitigation

Both knobs are plain env vars, so `settings.json` `env` can set them:

- `CLAUDE_PTY_HEARTBEAT_MS` — raise so a stalled CLI is not mistaken for a
  dead one. Attacks the trigger.
- `CLAUDE_PTY_ORPHAN_CHECK_MS` — raise to widen the 60s grace. Verified above.

**Cost:** a genuinely dead parent leaves its pty host and job running for the
full grace instead of 60s, so orphaned processes linger and must be reaped by
hand. This trades silent job loss for occasional process leaks.

This is an upstream defect. There is no seam in this repo to regression-test
it, so the harness above *is* the regression test: re-run it after a Claude
Code upgrade to see whether the behaviour changed.

## Why this matters for #597's other two asks

The file-readable worker progress #597 asks for is the actual defence. A
`SIGKILL`ed job cannot report anything, so the only survivable record is what
it already appended to disk before it died — which is exactly what the
progress-file rule buys. The wake is not recoverable; the work is.
