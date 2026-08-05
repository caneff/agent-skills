---
name: handoff
description: Compact the current conversation into a self-contained handoff document a fresh session can pick up. Default writes it to /tmp and tells you to /clear and /pickup; a leading mode word (agent / sub / side) instead launches an independent session, a sub-agent, or a background side-agent seeded with it.
argument-hint: "What the next session will focus on (prefix with agent | sub | side to launch instead of writing)"
disable-model-invocation: true
---

Write a self-contained handoff summary of the current conversation so a fresh agent can continue with only this summary — no dependency on the current session.

All modes share these rules:

- **Standalone.** Reference specs, plans, ADRs, issues, commits, and diffs by path or URL — do not duplicate them, and do not lean on context only this session holds.
- Include a **"Suggested skills"** section naming skills the next session should invoke.
- **Redact secrets** (API keys, passwords, PII).
- If the user passed a focus description, tailor the summary to it.

## Write the file (every mode)

Write the summary to `/tmp/handoff-<slug>.md`, where `<slug>` is a short kebab-case name for the work. Keep the word `handoff` in the filename so `/pickup` finds it.

## Then, depending on mode

Read the first word of the argument: `agent`, `sub`, or `side` selects that mode; anything else means File mode (the default). Remaining words are the focus description.

The three launch modes all seed the fresh agent the same cheap way — its prompt is just `Read the handoff at /tmp/handoff-<slug>.md and continue the work.` — so the summary lives in one place.

### File mode (default)

Tell the user to run these two commands, in order:

```
/clear
/pickup
```

`/pickup` finds this file (newest `*handoff*.md` in `/tmp`) and resumes the work. Don't do anything else — the current session is done once the file is written.

### Agent mode (`agent ...`) — independent, outlives this session

Hand the user a ready launch line that starts a fresh, top-level session — not a child of this one:

```
! claude --bg --name "<descriptive name>" "Read the handoff at /tmp/handoff-<slug>.md and continue the work."
```

Fill in a descriptive `--name`. It runs in the current working directory, outlives this session, and the user manages it with `claude agents`.

### Sub mode (`sub ...`) — child that reports back here

Spawn a fire-and-return subagent with the Agent tool: **no** `name`, `run_in_background: false`, prompt = the seed line above. It does the handed-off work and returns its result into *this* session. Use when you want the work done now and the answer back in the current thread.

### Side mode (`side ...`) — background teammate alongside this session

Spawn a persistent side-agent with the Agent tool: pass a descriptive `name`, `run_in_background: true`, prompt = the seed line above. It runs concurrently; you keep working and address it later with SendMessage. Use when the handed-off work should proceed in parallel without blocking you.
