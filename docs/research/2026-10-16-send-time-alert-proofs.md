# Send-time alert: the two facts #1540's ruling asked the builder to prove

Ruling (Chris, 2026-10-11, comment on #1540): the builder proves each fact
before relying on it. Both were run on 2026-10-16 from the #1540 worker's own
session.

## 1. A bare connect with no message does not disturb the receiving session

`resolve-controller` opens a connection to a session record's
`messagingSocketPath` and closes it, sending nothing.

Procedure: read `messagingSocketPath` from the worker's own live record in
`~/.claude/sessions/<pid>.json`, `socket.connect()` to it from Python, close at
once. The connect succeeded, the session (busy at the time) finished its turn
with no stray input, and the socket file stayed. A second connect to a path
under the same directory that does not exist raised `FileNotFoundError`.

What was not observed: the receiving process's internal state. A reviewer
repeated the connect on its own session and saw no new transcript line.

## 2. A PostToolUse hook fires on a failed `SendMessage`

Procedure: a scratch `PostToolUse` hook (matcher `SendMessage`) and a scratch
`PostToolUseFailure` hook, both appending their stdin to a log, in the
worktree's ignored `.claude/settings.local.json`. Then a `SendMessage` to a
name no session bears.

- The tool returned `{"success":false,"message":"No agent named '…' is
  reachable.\nUse ListAgents to see everyone you can message."}`.
- `PostToolUse` fired once. Its event carried `tool_name: "SendMessage"`,
  `tool_use_id`, `tool_input.to`, and
  `tool_response: {"success": false, "message": "...", "display": "Not sent — no agent named '…' is reachable."}`.
- `PostToolUseFailure` did not fire.

A schema-invalid send (a `to` holding a newline) failed in input validation
before any send; the scratch hooks were not reloaded for that second probe, so
it shows nothing about hook firing. A thrown tool error from `SendMessage`
that reaches `PostToolUseFailure` has not been observed, and
`worker-send-alert.sh` does not register for it. The 2026-10-08 episodes in
`docs/agents/friction-log.md` failed as `not reachable`, the shape above.
