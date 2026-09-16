# herdr sidebar clicks stall for ~30s, cured by alt-tab

Status: **one incident captured, cause not pinned.** `herdr.auto-title` is
disabled as of 2026-09-16 12:52Z as a live experiment — see *The experiment*
below. Whoever picks this up next: read *What is still unknown* before
re-chasing anything listed as already ruled out or already suspected.

## Symptom (Chris, 2026-09-16 08:41 local / 12:41Z)

Clicking an agent in herdr's sidebar does not switch to it. The UI appears
alive. Recovery: alt-tab to another VS Code window and back to the herdr
window, after which clicks work again immediately.

Reported as intermittent ("sometimes"), frequency unmeasured. herdr 0.9.0,
server running, socket `~/.config/herdr/herdr.sock`.

## What the evidence shows

`~/.config/herdr/herdr-server.log` logs every switch as a
`workspace.focus` / `tab.focus` pair. Across the incident there is a
**32-second hole with no focus event at all**, while the server's own
scheduled work continues:

```
12:40:36.145970  workspace focused  event="workspace.focus"  outcome="ok"  workspace_id="wD"
12:40:36.584948  api request received  request_id="auto-title-275795" method="tab.rename" changes_ui=true
12:40:36.586118  api request completed  request_id="auto-title-275795" method="tab.rename"
12:40:41.586463  session saved  event="persist.save"  workspaces=17
12:41:03.412043  session saved  event="persist.save"  workspaces=17
12:41:08.972044  workspace focused  event="workspace.focus"  outcome="ok"  workspace_id="w3H"
12:41:09.082224  api request received  request_id="auto-title-276056" method="tab.rename" changes_ui=true
12:41:09.563256  workspace focused  event="workspace.focus"  outcome="ok"  workspace_id="wD"
```

Established facts:

1. **The clicks never reached the server.** No `workspace.focus` request
   arrives for 32s. Every focus that does arrive, before and after, is
   `outcome="ok"` — so this is not a switch that failed, it is a switch that
   was never requested.
2. **The server was alive throughout**, writing `persist.save` at 12:40:41
   and 12:41:03.
3. **A focus event cured it.** The first request after the hole
   (12:41:08.97) is the alt-tab-and-back, and normal switching resumes from
   there.

So the failure is on the path from the client's input handling to the API
socket, not in the server's handling of a switch.

## The experiment now running

`herdr.auto-title` v0.5.0 (`github:kryptamine/herdr-auto-title@7fcec81`,
a Go binary herdr launches at startup) is the standing suspect, for one
timing reason only: the hole is bracketed by its `tab.rename` calls — the
last one lands 0.44s before the silence begins, the next one 0.11s after it
ends — and herdr tags each of those `changes_ui=true`.

Disabled 2026-09-16 12:52Z:

```
herdr plugin disable herdr.auto-title   # -> enabled: false
kill <pid>                              # disable does not stop the running binary
```

The binary is a self-supervising one-shot launch, so `disable` alone leaves
it running; it had to be killed separately (pid 7014 that day). Re-enable
with `herdr plugin enable herdr.auto-title`, which may need a herdr restart
to relaunch it. Cost while disabled: tab titles are plain "Claude Code"
instead of contextual.

Reading the result:

- **Stalls stop** → the plugin. Report goes to `kryptamine/herdr-auto-title`
  with the log excerpt above.
- **Stalls continue** → the plugin is cleared. Report goes upstream to herdr
  0.9.0.

## Ruled out

- **The Wispr / Kitty keyboard-protocol paste bug** (fixed 2026-09-14, see
  `flow/claude/OPERATIONS.md`). Both halves of that fix are still in place:
  `shift+insert` → `workbench.action.terminal.paste` in
  `/mnt/c/Users/canef/AppData/Roaming/Code/User/keybindings.json`, and
  `terminal.integrated.enableKittyKeyboardProtocol: true` in `settings.json`.
  Different symptom anyway — that one is a pane refusing pasted text.
- **Machine load.** At the time of checking: load 7.2 on 32 cores, 9 GB of
  39 used, no swap, `herdr` itself at 2.2% CPU after 11 hours. The hottest
  processes were another agent's Python jobs in a sudokumaker worktree.
- **A wedged or slow herdr server.** `herdr status --json` returns in 0.00s,
  three runs; and see fact 2 above.
- **Blocked panes.** No pane was in `blocked` state, and
  `~/.claude/worker-stop-alerts.log` has zero `not-sent` lines, so no hook
  had failed to reach a pane that day either.
- **A VS Code extension.** herdr's sidebar is its own TUI, not an extension;
  there is no herdr channel in the VS Code exthost logs.

## What is still unknown

- Whether the 32-second duration and the alt-tab cure are consistent across
  incidents, or particular to this one. **Two more timestamped incidents
  would settle it.** Chris reports the time; the log excerpt is then a
  `rg "2026-09-DDT<HH>:<MM>" herdr-server.log` away.
- Whether the client drops the input or never reads it — the log only shows
  the server's side, and `~/.config/herdr/herdr-client.log` has not been
  written since 2026-09-15, so it carries nothing about this.
- Whether window occlusion or focus state is the trigger, which the alt-tab
  cure hints at but does not establish.

## Corrections made while investigating this

Both of these were my own inferences, stated before checking, and both were
wrong — recorded so nobody rebuilds an argument on them:

- "auto-title makes ~270 API calls in 33s." False. That came from reading
  the global `request_id` counter (275795 → 276067) as if the ids were the
  plugin's alone. Actual `tab.rename` entries in the whole log: 930,
  arriving in ones and twos. The plugin polls twice a second but only calls
  the API when a title actually changes.
- "The plugin went quiet during the hole too, so two clients stalled at
  once." Unsupported. Renames are event-driven, so their absence across the
  hole means only that no title changed.

Filed from: conversation, 2026-09-16.
