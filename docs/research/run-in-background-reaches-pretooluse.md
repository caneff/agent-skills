# Does `run_in_background` reach a `PreToolUse` hook?

**Yes.** Claude Code 2.1.263 puts `run_in_background` in `tool_input` on the
`PreToolUse` payload for the `Bash` tool, and a hook's `updatedInput` is honoured.
Automatic wrapping (#671) can be built as written; no heuristic over the command
text is needed.

Probed 2026-09-08 for #667, a slice of spec #597. Claude Code version tested:
`2.1.263`. Nothing live was touched — the probe registers a throwaway hook through
`claude --settings <temp file>`, which is read-only with respect to
`~/.claude/settings.json`, and leaves nothing behind when the temp dir goes.

## Repro

```bash
P=$(mktemp -d)
cat > "$P/dump.sh" <<EOF
#!/usr/bin/env bash
cat >> "$P/payloads.jsonl"; printf '\n' >> "$P/payloads.jsonl"; exit 0
EOF
chmod +x "$P/dump.sh"
cat > "$P/settings.json" <<EOF
{ "hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [
  { "type": "command", "command": "$P/dump.sh" } ] } ] } }
EOF
claude -p --settings "$P/settings.json" --allowedTools Bash --model sonnet \
  'Run exactly one Bash tool call, in the background (run_in_background: true), with the command: sleep 2; echo probe-done. Then reply with only the word OK.' </dev/null
jq . "$P/payloads.jsonl"
```

## The payload, verbatim

```json
{
  "session_id": "521179f1-b4dd-4fd4-b1b4-f036730b44b4",
  "transcript_path": "/home/caneff/.claude/projects/-home-caneff-orca-workspaces-skills-implement-spec-597/521179f1-b4dd-4fd4-b1b4-f036730b44b4.jsonl",
  "cwd": "/home/caneff/orca/workspaces/skills/implement-spec-597",
  "prompt_id": "0a830051-7e2d-4780-ac02-8533c59a0aaf",
  "permission_mode": "auto",
  "effort": { "level": "medium" },
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "sleep 2; echo probe-done",
    "run_in_background": true
  },
  "tool_use_id": "toolu_01WdFX5uCX93XppNue4BvLii"
}
```

A foreground call through the same rig carries the field explicitly as `false`:

```json
{"command":"echo fg-probe","description":"Echo probe string","run_in_background":false}
```

A hook must still treat an **absent** field as foreground: the model chooses whether
to emit it, and only `true` is a positive signal.

## `updatedInput` works

A hook returning

```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"( echo BASE ) ; echo TAG","run_in_background":true}}}
```

caused the rewritten command to run: the background job's output was `BASE` then
`TAG`. So the wrapping mechanism #671 depends on is real, not just documented.

## Two rewriting hooks on one matcher race — the ordering risk, measured

The spec's "Ordering risk" note asked what wrapping around an already-rewritten
command does. The answer is worse than an ordering question.

Registering two rewriting hooks on the `Bash` matcher and running the same
background call repeatedly:

- **Each hook receives the original `tool_input`,** not the other's output. The
  second hook saw `"echo BASE"`, never the first hook's rewrite. Rewrites do not
  chain.
- **Exactly one `updatedInput` survives, and which one is not deterministic.**
  With the hook list in a fixed order, two consecutive runs executed
  `( echo BASE ) ; echo TAG-ONE` and `( echo BASE ) ; echo TAG-TWO` respectively.
  It is a race, not a position rule.

This matters because `rtk hook claude` is already registered on that matcher and
**does** rewrite background calls:

```console
$ printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status","run_in_background":true}}' | rtk hook claude
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecisionReason":"RTK auto-rewrite","updatedInput":{"command":"rtk git status","run_in_background":true}}}
```

It stays silent for a command it does not proxy (`sleep 60; echo hi` → no output),
so the collision is confined to background calls whose command rtk recognises.

**Consequence for #672:** registering `job-run`'s hook as a second rewriter beside
`rtk hook claude` would, for those commands, drop the `job-run` wrapper at random —
recreating the exact hole #597 exists to close, an agent believing in a record that
was never written. Registration must leave **one** producer of `updatedInput` for
background Bash calls. `block-dangerous-git.sh` is not part of the problem: it only
ever exits 0 or 2 and never emits JSON.
