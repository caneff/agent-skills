# herdr multi-agent coordination: what a controller can use to fan in on N workers

## Summary

herdr 0.9.0 has no CLI wait-any and no documented "wait for any of these agents"
primitive. A controller has four real options, in ascending sophistication:

1. **Per-agent `agent wait` loop** — spawn a wait per worker (sequentially or as
   concurrent shell jobs) and poll for the first to return. Fully documented,
   zero setup, but is either serial (head-of-line blocking) or requires the
   controller to manage N background processes itself.
2. **`api snapshot` polling** — poll the whole-session state on an interval and
   diff `agent_status` per pane/agent. Documented via the CLI wrapper; costs a
   full session dump every poll (agents, panes, tabs, workspaces, layouts) with
   no server-side filtering, and burns whatever interval you pick — no
   push/wake.
3. **`events.subscribe` with one `pane.agent_status_changed` subscription per
   worker pane, on one socket connection** — a real, documented, working
   wait-any: the controller keeps one connection open, lists N subscriptions
   in the `subscriptions` array, and the first worker to change state pushes
   an event on that connection. This is confirmed directly by a herdr
   maintainer as the intended answer to "avoid polling loops," but it is
   socket-API only — there is no `herdr events subscribe` CLI wrapper, so a
   controller needs a raw newline-delimited-JSON socket client (or to shell
   out to something that speaks it) rather than plain `herdr` CLI calls.
4. **`notification.show` / OS toast** — one-way, user-facing, not a
   programmatic fan-in signal a controller script can block on.

There is no `events.wait` that accepts multiple targets: `events.wait` takes
one `match_event` (a single EventMatch), so it collapses to option 1's
semantics if used per-agent. The array-of-subscriptions form is on
`events.subscribe`, not `events.wait`.

No first-party inter-agent messaging exists yet. A June 2026 community
discussion proposes agent-to-agent task delegation (A2A protocol or a custom
minimal protocol) precisely because herdr's own primitives (`agent.send`,
`agent.read`, `agent.list`) have "no higher-level protocol for one agent to
address another by name, delegate a sub-task, or await a result" — still an
open design discussion, not shipped. A related idea, "reliable queued
delivery with sender attribution," was split out as a prerequisite and is
also unshipped.

One published third-party artifact drives N herdr agents today: a
`herdr-multi-agent` skill (community plugin repo, not herdr's own) that
encodes *judgment* for fan-out (council / pipeline / manager-worker shapes)
but for the actual wait mechanism defers to the vendored herdr skill's
per-agent `agent wait --until <status>` recipe — i.e., it uses option 1, not
`events.subscribe`.

## Options table

| Option | Mechanism | Cost | Documented or inferred | Exact command / call |
|---|---|---|---|---|
| Per-agent wait loop | `herdr agent wait <target> --until <status>` per worker | One process/wait per worker; serial unless the controller backgrounds each wait itself | Documented (CLI reference, agent-automation.mdx) | `herdr agent wait w1J:p1 --until idle --until done` |
| `agent prompt --wait` | Submits + waits in one call, avoiding a submit/wait race | Same as above, one call per worker | Documented | `herdr agent prompt reviewer "..." --wait --timeout 120000` |
| Snapshot polling | `herdr api snapshot` (wraps socket `session.snapshot`) on an interval, diff `agent_status` per entry in `.result.snapshot.agents[]` | Full session JSON every poll (all agents/panes/tabs/workspaces/layouts, not filtered); interval tradeoff between latency and load | Documented (`herdr api` --help, socket-api.mdx: "not a subscription") | `herdr api snapshot` |
| Multi-subscription event stream (true wait-any) | Socket `events.subscribe` with a `subscriptions` array containing one `{"type":"pane.agent_status_changed","pane_id":..., "agent_status": ...}` entry per worker pane, on one open connection; first pushed event on that connection is your wait-any hit | One long-lived socket connection; zero poll cost; pushed events only, no CLI wrapper exists (must speak newline-delimited JSON over `HERDR_SOCKET_PATH`) | Documented in socket-api.mdx **and explicitly confirmed by a herdr maintainer** as the answer to "avoid polling loops" (issue #4027, closed as already-supported) | `{"id":"sub_1","method":"events.subscribe","params":{"subscriptions":[{"type":"pane.agent_status_changed","pane_id":"w1J:p1"},{"type":"pane.agent_status_changed","pane_id":"w1K:p1"}]}}` |
| `events.wait` | Socket one-shot wait for a single `EventMatch` | One target only — same fan-in ceiling as option 1 if you call it N times | Documented in the JSON schema (`herdr api schema --json` → `request.$defs.EventsWaitParams`); not mentioned in socket-api.mdx prose | `{"id":"w1","method":"events.wait","params":{"match_event":{"event":"pane_agent_status_changed","pane_id":"w1J:p1","agent_status":"idle"}}}` |
| `notification.show` | OS/toast notification on state change | Fire-and-forget, human-facing, not scriptable as a wait | Documented | `herdr notification show "build failed" --sound request` |
| Workspace-wide/fleet-wide watch (no explicit target list) | N/A | N/A | **Not found** — explicitly declined. Maintainer: "A workspace-wide watch, per-workspace transition hook, or multi-target CLI wait would be a new interface rather than a fix to existing behavior." (issue #4027, closed as feature request) | — |
| Native agent-to-agent messaging / delegation (`@agent` addressing, task await) | N/A | N/A | **Not found** — open community proposal only (discussion #741, "Inter-agent communication & @agent task delegation," opened 2026-06-22, unresolved as of this research); a prerequisite primitive ("reliable queued delivery with sender attribution") was split into its own idea and is also unshipped | — |

## Sources

- `herdr --skill` (installed binary, herdr 0.9.0) — CLI control surface, `agent wait`/`agent prompt --wait` semantics.
- `herdr agent`, `herdr agent wait --help`, `herdr agent get --help`, `herdr api`, `herdr api schema`, `herdr api schema --json`, `herdr notification`, `herdr notification show --help`, `herdr --help` — all run locally against the installed 0.9.0 binary.
- `herdr api snapshot` (live output) — confirms `session.snapshot` shape and cost (full agents/panes/tabs/workspaces/layouts dump, no filter param).
- Full JSON API schema (`herdr api schema --json`, protocol 22, schema_version 1) — `request.$defs.EventsSubscribeParams`, `EventsWaitParams`, `EventMatch`, `Subscription`, `AgentWaitParams`; `subscription_event.$defs.SubscriptionEventKind`, `PaneAgentStatusChangedEvent`, `PaneOutputMatchedEvent` — establishes that `events.subscribe` takes an array of subscriptions (multi-target) while `events.wait` takes one `EventMatch` (single-target), and that there is no CLI command group for either (`herdr events` → `unknown command: events`).
- https://herdr.dev/agent-guide.md — human-onboarding guide; points to CLI reference and socket API for automation, no multi-agent recipe of its own.
- https://herdr.dev/llms.txt — documentation index used to locate `socket-api.mdx` and `agent-automation.mdx` at the pinned `v0.9.0` doc revision.
- https://raw.githubusercontent.com/herdrdev/herdr/v0.9.0/docs/next/website/src/content/docs/socket-api.mdx — canonical source for the raw method table (including `events.subscribe`, `events.wait`), the `events.subscribe` example showing multiple `pane.agent_status_changed` subscriptions on one connection, and the explicit statement that `session.snapshot` "is not a subscription."
- https://raw.githubusercontent.com/herdrdev/herdr/v0.9.0/docs/next/website/src/content/docs/agent-automation.mdx — canonical source for the documented recipes; every worked example targets one agent at a time (start helper → prompt → wait; wait for blocked → read → send-keys), no N-agent recipe.
- https://github.com/herdrdev/herdr/issues/4027 — "Fleet-level agent state-transition events for orchestrating sessions (avoid polling loops)," closed by maintainer `akbash-bot` (collaborator) with the direct statement that `events.subscribe` with several `pane.agent_status_changed` subscriptions on one connection already avoids polling/a shell per agent, and that a workspace-wide watch or multi-target CLI wait is an unshipped new interface.
- https://github.com/herdrdev/herdr/issues/4052 — "agent prompt has no wait-if-busy / refuse-if-busy option," closed as feature request; confirms `agent prompt --wait` can prompt an already-working agent and does not reserve/isolate tasks (relevant if a controller pipes work to a busy worker).
- https://github.com/herdrdev/herdr/issues/3820 — "Expose client-level aggregate agent list, events, and focus for multi-machine plugins," closed as feature request; confirms the CLI/API is server-scoped (one herdr server = one fan-in domain; no cross-machine aggregate view).
- https://github.com/herdrdev/herdr/discussions/741 — "Inter-agent communication & @agent task delegation for herdr," opened 2026-06-22 by herdrdev, open/unresolved; documents that no native agent-to-agent addressing, delegation, or await-a-result protocol exists, and that a `reliable queued delivery with sender attribution` idea was split out as a prerequisite.
- https://github.com/jbaham2/herdr-plugin/blob/main/skills/herdr-multi-agent/SKILL.md — third-party published skill for running a fleet of herdr agents (council / pipeline / manager-worker patterns); for the actual wait mechanism it defers to the vendored herdr skill's per-agent `agent wait`/`agent status` recipe, i.e. it does not use `events.subscribe`.
