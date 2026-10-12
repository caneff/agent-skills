# Can a mod wake an idle session? (2026-10-12)

Question (#1367, gating the job-wake mod #1371 of spec #1365): can a mod
running inside an idle Claude Code session start a turn in that session by
itself, with no input from the person?

## Answer

**Yes. `$.prompt.submit` from a `$.clock.after` timer starts a turn in an idle
session.** ADR 0003 does not reopen, and job-wake can be built on this call.

The model reads the prompt as a user turn wrapped in the engine's own framing,
which names the plugin:

```
The wake-probe plugin sent a message:
wake-probe submit: reply with the single word WOKEN.

This is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. Address the message above.
```

The terminal shows it under a `› Prompt from the wake-probe plugin` heading,
and the model answered `WOKEN`.

## What was tried

| Call | Result, verbatim | Turn started |
|---|---|---|
| `$.prompt.submit({ text })` | resolved `{"text":"wake-probe submit: reply with the single word WOKEN.","origin":{"kind":"plugin","name":"wake-probe"}}` | yes, 83 ms after the timer fired |
| `$.session.append` | not tried | — |
| `$.session.send` to itself | not tried | — |

The ticket asks for the other two only if `$.prompt.submit` fails. It did not.

## Not covered

- One run, one idle wait of 20 s. A session idle for hours was not tried.
- The session had taken one typed turn first. A session that never had a
  prompt was not tried.
- The session was not parked on a permission dialog or any other dialog.
- The session ran in a detached tmux pane with no client attached, in auto
  mode (the box default), on Haiku. A herdr pane was not tried.
- `claude -p` and SDK hosts were not tried.

## Method

Claude Code 2.1.296, WSL. A throwaway mod, `wake-probe`, loaded with
`--plugin-dir` into an interactive session started in a private tmux server
(`tmux -L probe1367`), cwd an empty scratch folder. herdr, messaging and
parent-session variables were unset for the child. `CLAUDE_CODE_PLUGIN_DIRS`
was unset too, but the user settings' `env` block set it again, so
`agent-model` loaded beside the probe.

1. Start: `claude --plugin-dir <probe-mod> --model haiku --debug-file <log>`,
   with `PROBE_CALL=submit PROBE_DELAY_MS=20000 PROBE_LOG=<file>`.
2. Accept the workspace-trust dialog. Hooks modules do not load before it:
   the debug log says `hooks modules not loaded until workspace trust is
   accepted`.
3. Type one prompt, `Reply with the single word READY.`, and touch nothing
   after it.
4. The mod's `turn.complete` hook arms `$.clock.after(20000, ...)`. The timer
   calls `$.prompt.submit` and logs what it resolves to. The mod's
   `turn.start` and `prompt.submit` hooks log every turn.

The mod's own log, whole:

```
2026-10-12T17:26:38.940Z session.start {"isInteractive":true,"surface":"terminal","call":"submit"}
2026-10-12T17:26:49.151Z prompt.submit seen {"text":"Reply with the single word READY.","wait":false,"origin":{"kind":"composer"}}
2026-10-12T17:26:49.231Z turn.start {"text":"Reply with the single word READY.","turnId":"9a7d5e33-f783-4bce-b76c-23326c75c077"}
2026-10-12T17:26:50.263Z turn.complete
2026-10-12T17:26:50.281Z timer armed {"call":"submit","ms":20000}
2026-10-12T17:27:10.283Z timer fired {"call":"submit"}
2026-10-12T17:27:10.366Z turn.start {"text":"The wake-probe plugin sent a message:\nwake-probe submit: reply with the single word WOKEN.\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. Address the message above.","turnId":"d16e9996-0d53-4bc5-807f-4838f7b62052"}
2026-10-12T17:27:10.366Z call resolved {"text":"wake-probe submit: reply with the single word WOKEN.","origin":{"kind":"plugin","name":"wake-probe"}}
2026-10-12T17:27:11.686Z turn.complete
2026-10-12T17:27:40.376Z DONE
```

The typed prompt carries `origin.kind` `composer`; the mod's carries `plugin`.
The mod's own `prompt.submit` hook did not see the prompt it submitted. The
debug log says why: `hooks module wake-probe@inline prompt.submit skipped:
re-entry (the plugin's own code raised it; origin wake-probe)`. The classic
`UserPromptSubmit` settings hooks did run on it.

The call resolved as the turn started, not when it ended: `call resolved` and
the second `turn.start` share a timestamp, 1.3 s before `turn.complete`.

## Cleanup

`tmux -L probe1367 kill-server` ended the session. Afterwards the process
table held no `claude --plugin-dir` process and the tmux server was gone.
Accepting the trust dialog left one trust entry for the scratch folder in
`~/.claude.json`.

## The probe mod

Scratch, never in the tree. `hooks/register.ts`, with a `plugin.json` naming
it `wake-probe` and a `hooks.json` listing the module:

```ts
import type { Register } from 'claude-code'

// Throwaway probe for #1367. After the first turn completes it waits
// PROBE_DELAY_MS with the session idle, then makes the one call PROBE_CALL
// names and logs what came back and whether a turn started.
const lines: string[] = []
let path = ''
let armed = false

async function log($: any, what: string, data?: unknown): Promise<void> {
  const at = new Date(await $.clock.now()).toISOString()
  lines.push(`${at} ${what}${data === undefined ? '' : ' ' + JSON.stringify(data)}`)
  if (path) await $.fs.write(path, lines.join('\n') + '\n')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    path = (await $.env.get('PROBE_LOG')) ?? ''
    await log($, 'session.start', { isInteractive: e.isInteractive, surface: e.surface, call: await $.env.get('PROBE_CALL') })
    return next(e)
  })
  on('prompt.submit', async ($, e, next) => {
    await log($, 'prompt.submit seen', e)
    return next(e)
  })
  on('turn.start', async ($, e, next) => {
    await log($, 'turn.start', e)
    return next(e)
  })
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    await log($, 'turn.complete')
    if (armed) return result
    armed = true
    const call = (await $.env.get('PROBE_CALL')) ?? 'submit'
    const ms = Number((await $.env.get('PROBE_DELAY_MS')) ?? '20000')
    const text = `wake-probe ${call}: reply with the single word WOKEN.`
    await log($, 'timer armed', { call, ms })
    $.clock.after(ms, () => {
      void (async () => {
        await log($, 'timer fired', { call })
        try {
          let out: unknown
          if (call === 'submit') out = await $.prompt.submit({ text })
          else if (call === 'append')
            out = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
          else if (call === 'send-id')
            out = await ($.session.send as any)({ to: { sessionId: await $.session.id() }, text })
          else if (call === 'send-str')
            out = await ($.session.send as any)({ to: await $.session.id(), text })
          else out = `unknown call ${call}`
          await log($, 'call resolved', out)
        } catch (err) {
          await log($, 'call rejected', String((err as Error)?.message ?? err))
        }
        $.clock.after(30000, () => void log($, 'DONE'))
      })()
    })
    return result
  })
}
```
