# Prototype: N workers to one controller over the sessions socket

Ticket: [Prototype: N workers to one controller over the sessions socket](https://github.com/caneff/agent-skills/issues/778), map #776.
Date: 2026-09-13 (UTC 2026-09-14 03:10–03:24). Throwaway branch `prototype/socket-fanin`.

## Question

Does N-to-1 fan-in over the Claude sessions socket wake an idle controller reliably, and what
happens when the controller is blocked inside a tool call or a worker vanishes?

## Setup

Four throwaway claude sessions (sonnet) in their own worktrees under herdr, started exactly the way
`implement-dispatch` starts a worker (`herdr worktree open` → `herdr agent start --kind claude`):
one controller (`proto-fanin-ctl`, registry name `proto-fanin-ctl-94`) and three workers
(`proto-fanin-1..3`). Briefs: the controller does nothing until a peer message arrives, then replies
`got: <text>` and ends its turn; a worker, when prompted `SEND ...` through `herdr agent prompt`,
calls `SendMessage` to the controller and ends its turn. Scripts and the raw timeline are in
`socket-fanin-prototype/` next to this file; the timeline is read from the four transcripts
(`~/.claude/projects/*/<sessionId>.jsonl`): a worker's `SendMessage` tool_use record and the
controller's `attachment.origin.kind == "peer"` record or user-turn record.

## Rounds and results

| Round | Controller state | Sends | Result |
|---|---|---|---|
| A | idle at prompt | staggered, 45 s apart | each message became a new user turn 1.0–1.3 s after the send; reply 1.5 s later; nothing waited |
| B | blocked in a 150 s tool call (`node -e setTimeout`) | staggered at +20/+60/+100 s | all three written to the transcript within 1.4 s of the send as `queued_command` attachments, but shown to the model only when the tool returned; first message waited 133 s; none lost; order kept |
| C | idle at prompt | burst, three sends within 0.33 s | first send woke the controller as a turn 0.65 s later; the other two queued and landed as two user-turn records 80 ms after the first reply, answered together in one reply; none lost; order = send order |
| D | any | worker 3 runs `/exit` | within 8 s: `herdr agent get` → `agent_not_found`, `~/.claude/sessions/<pid>.json` gone, pid gone |

## The wait contract for a controller over N workers

1. **An idle controller is woken by a worker's `SendMessage`.** Delivery is a fresh user turn about
   one second after the call. The operations doc's line "a worker's message arrives at the
   controller's next tool round" is true only while the controller is *working*; for an idle
   controller the message is the next turn. The doc line is corrected in this change.
2. **A blocked controller hears nothing until its tool returns.** Messages are not lost; they are
   held and presented when the tool call ends. So the controller must never sit in a long tool call
   (a long `sleep`, `herdr agent wait` with no timeout, a blocking `TaskOutput`) while it expects
   worker reports; the wait *is* going idle.
3. **Concurrent reports are serialized, not coalesced.** A burst becomes one turn per message (the
   later ones arrive as separate queued records answered in the same reply). No message merged
   into another, none dropped, order preserved.
4. **A worker that exits is detectable by polling only.** `herdr agent get <name>` returns
   `agent_not_found` and the sessions-registry file disappears within seconds. There is no push
   signal for an exit; the only push-shaped option is `SendMessage` with `notify_when_idle: true`
   (one-shot, one notice on idle or exit), which the controller would have to re-arm after every
   notice. See the `notify_when_idle` note below.
5. **Fan-in needs no herdr socket client.** The sessions socket gives the controller wait-any for
   free: N workers, one idle controller, each report a turn. herdr's `events.subscribe` (research
   ticket #777) stays a fallback for a worker that cannot run `SendMessage` (a non-Claude agent).

### `notify_when_idle` note

A subscription was placed on worker 2 (with a message) and the worker was then exited. Whether the
one-shot notice arrived at the subscribing session, and whether it distinguished idle from exit, is
recorded in the ticket's resolution comment (the notice lands in the subscriber's own transcript
after this file was written).

### herdr gotchas met on the way

- `herdr agent prompt ... --wait --until idle` timed out on every worker although each had ended
  its turn: herdr reported the state as `done`, not `idle`. Pass `--until idle --until done`.
- `herdr worktree open` returns the pane at `result.root_pane.pane_id` and the workspace at
  `result.workspace.workspace_id` (as `implement-dispatch` already reads them); `herdr pane list`
  with a wrong workspace id fails with `workspace_not_found`.

## Verdict

Yes: N-to-1 fan-in over the sessions socket wakes an idle controller reliably, with no loss and no
coalescing at N=3, so the multi-worker controller's wait is "go idle and let workers report".
The two rules the spec must carry: the controller never blocks in a long tool call while workers
are out, and a silent worker is found by polling `herdr agent get` plus the sessions registry, not
by waiting for a message.
