# style-blind-test activation

Manual on/off switch for the harness:

```
python3 style-blind-test/activate.py install
python3 style-blind-test/activate.py uninstall
```

`install` wires the SessionStart and UserPromptSubmit hooks into
`~/.claude/settings.json`, sets `outputStyle` to `default` (blanking the
native style), and disables the existing "stay in that voice" echo
reminder for the duration of the test -- it would otherwise fire every
turn regardless of the coin flip and contaminate Experiment 2. `uninstall`
restores everything, including the echo reminder. `install` is idempotent:
running it twice prints "already active" and does not touch settings again.

Criterion 4 -- confirming a real session shows the injected style live --
is a MANUAL check: run `install`, start a Claude Code session and look, then
run `uninstall` when done.

## Loud reminder

`install` also wires a `Stop` hook (`stop_reminder.py`) that counts assistant
turns per session in `~/.claude/style-blind-test/turns/<session_id>`. Every
`QUALIFYING_TURNS`-th turn (10, 20, 30, ...) it fires once: a terminal bell
plus a WSL desktop toast (via this skill's `toast.ps1`, a no-op when
`powershell.exe` isn't on PATH) reading "Blind test -- log your guess (gs)".
It never reveals the style and never touches the guess log.

Exactly when a toast fires, `stop_reminder.py` also writes a global marker
file, `~/.claude/style-blind-test/last_toast`, naming that toast's session id
and its `cwd`. Non-firing turns never touch the marker. This is what `gs`
reads to know which session a toast was actually for -- see below.

## `gs` / `fin` quick-capture

Add this to `~/.bashrc` (not done automatically):

```bash
gs()  { python3 /home/caneff/.agents/skills/style-blind-test/capture.py gs "$@"; }
fin() { python3 /home/caneff/.agents/skills/style-blind-test/capture.py fin "$@"; }
```

`gs` prints a numbered menu of the four `STYLES` with a one-line description
of each, then prompts "which style is active? [1-4]" and "how confident are
you in that guess? [l/m/h]  (low / medium / high)", then logs the guess
through the same side channel `capture.py guess` uses. `fin` prompts "how
strong was the voice this session? [1-5]  (1 = barely there, 5 =
unmistakable)" and "did the voice fade as the session went on? [y/n]" for
the end-of-session strength rating. Both reject bad input (still 1-4 /
l/m/h / 1-5 / y-n tokens) and write nothing on rejection.

Run these in a **separate terminal**, never through Claude's `!` -- the model
must not see the guess or the blind breaks.

`gs` finds the session on its own, in this order: `--session-id <id>`, then
the global last-toast marker (`~/.claude/style-blind-test/last_toast`, written
the instant a toast fires), then `CLAUDE_CODE_SESSION_ID`, then the newest
file in `~/.claude/style-blind-test/turns/` (a fallback for when no toast has
fired yet). A toast means "log your guess", so `gs` is anchored globally to
whichever session's toast fired last, regardless of which terminal or
directory `gs` is typed in -- the header names the session the last toast
fired for, and that session's directory:

```
Recording guess for my-proj · a1b2c3d4 (a1b2c3d4-...)
```

The directory only shows when it genuinely belongs to the session being
recorded (the resolved session equals the marker's session); otherwise it
prints `?` rather than guessing. Pass `--session-id` to override the marker
entirely.
