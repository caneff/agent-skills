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
