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
`QUALIFYING_TURNS`-th turn (25, 50, 75, ...) it fires once: a terminal bell
plus a WSL desktop toast (via `sandcastle-watch/toast.ps1`, a no-op when
`powershell.exe` isn't on PATH) reading "Blind test -- log your guess (gs)".
It never reveals the style and never touches the guess log.

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
`CLAUDE_CODE_SESSION_ID`, then the newest file in
`~/.claude/style-blind-test/turns/` (the reminder hook writes one per turn).
A side terminal doesn't inherit `CLAUDE_CODE_SESSION_ID`, so auto-detect is
the usual path -- just type `gs` while the reminder hook is active. Caveat:
"newest file wins" picks the wrong session if two run at once; pass
`--session-id` to be explicit.
