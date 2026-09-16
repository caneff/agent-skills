# Codex CLI usage/quota percentage: sources and robustness

Summary: the on-disk rollout JSONL our `codex-usage.py` helper reads is still
the current wire shape in Codex CLI 0.154.0 (installed here) and in
upstream `main`, and `codex migrate-rollouts` does not change that — its
"paginated thread history" SQLite store (`~/.codex/thread_history_1.sqlite`)
holds UI items (messages, tool calls) but not `rate_limits`/`token_count`
telemetry, so the rollout file remains the only on-disk copy. Separately,
there **is** a first-party, no-model-turn way to get the number: the
`codex app-server` JSON-RPC method `account/rateLimits/read`, which calls a
dedicated backend endpoint (`GET /api/codex/usage`). OpenAI has stated in a
GitHub issue that the rollout file format is explicitly *not* a durable
surface, while the App Server API *is* documented/designed as one — the
opposite of what our current helper relies on. Several third-party tools
already read rollout files the same way we do (and hit the same fragility);
one (CodexFuse) uses `account/rateLimits/read` directly.

## 1. Where the rate-limit numbers live on disk

- Confirmed on this machine: `codex --version` → `codex-cli 0.154.0`. The
  newest rollout
  (`~/.codex/sessions/2026/09/14/rollout-2026-09-14T20-38-04-*.jsonl`)
  contains lines like:
  `{"type":"event_msg","payload":{"type":"token_count","info":{...},"rate_limits":{"limit_id":"codex","primary":{"used_percent":6.0,"window_minutes":10080,"resets_at":1789824776},"secondary":null,"credits":{...},"plan_type":"plus",...}}}`
  — same shape our helper (`~/.agents/skills/flow/ccstatusline-table/helpers/codex-usage.py`) already parses.
- `codex migrate-rollouts --help` describes itself as "Inspect or migrate
  legacy local sessions to **paginated thread history**." Running
  `codex migrate-rollouts --json` here reported every local session as
  `"status": "already_paginated"` — this CLI version already maintains that
  store.
- The paginated store is a local SQLite database,
  `$CODEX_HOME/thread_history_1.sqlite` (confirmed by inspecting this
  machine's file: 49 MB, tables `thread_turns`, `thread_items`,
  `thread_history_projection_state`, `thread_realtime_items`). Its
  `item_type` values are UI items: `userMessage`, `agentMessage`,
  `commandExecution`, `mcpToolCall`, `reasoning`, `webSearch`, `fileChange`,
  `subAgentActivity`, `collabAgentToolCall`, `imageView`, `imageGeneration`,
  `contextCompaction`. There is **no `token_count`/`rate_limits` item type**
  in this store — checked directly against the local DB; the only
  `item_json` rows matching the string `rate_limits` were a coincidental
  substring inside a `commandExecution` shell-output blob, not a real field.
  So migration to paginated history does not carry rate-limit snapshots
  forward; the rollout `.jsonl` remains the sole on-disk copy of
  `rate_limits`.
- Source confirms the wire shape is still current: in
  `codex-rs/thread-store/src/local/rollout_migration/line_parser.rs`
  (upstream `main`), the *legacy*-compat function
  `normalize_legacy_rate_limit_resets` only rewrites `resets_at` from an
  RFC3339 string to a Unix timestamp for `event_type == "token_count"`
  records — i.e., the current/target shape is exactly
  `payload.rate_limits.{primary,secondary}.{used_percent,resets_at}` with
  `resets_at` as an epoch integer, matching what's on disk here.
  [line_parser.rs](https://github.com/openai/codex/blob/main/codex-rs/thread-store/src/local/rollout_migration/line_parser.rs)
- Struct/serde names on the wire side: `codex-rs/codex-api/src/rate_limits.rs`
  defines `RateLimitSnapshot`/`RateLimitWindow` (from
  `codex_protocol::protocol`) and parses them from HTTP response headers
  (`x-codex-primary-used-percent`, `-window-minutes`, `-reset-at`, etc.) when
  hitting the Responses API directly — a second, header-based source of the
  same numbers, used internally by the API client on every model call.
  [rate_limits.rs](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/rate_limits.rs)

## 2. First-party way to ask for usage directly — yes, it exists

- `codex app-server` (JSON-RPC 2.0-like protocol, JSONL over stdio by
  default, also unix-socket/websocket) exposes method
  **`account/rateLimits/read`**, params `GetAccountRateLimitsParams`
  (optional; `supports_luna_reserve`, `exclude_reset_credit_details`),
  response `GetAccountRateLimitsResponse` with `rate_limits`,
  `rate_limits_by_limit_id`, `rate_limit_reset_credits`, `account_id`,
  `ordinary_usage_allowed`. Defined in
  [`codex-rs/app-server-protocol/src/protocol/v2/account.rs`](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/account.rs)
  and wired into
  [`ClientRequest`](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/ClientRequest.ts)
  as `{ "method": "account/rateLimits/read", id, params? }`.
- Handler:
  `codex-rs/app-server/src/request_processors/account_processor.rs`,
  `get_account_rate_limits_response`, calls
  `client.get_rate_limits_with_reset_credits()` /
  `get_rate_limits_with_luna_reserve()`, which issue a plain `GET` to
  `rate_limit_status_url()` — `{base_url}/api/codex/usage` (Codex API path
  style) or `{base_url}/wham/usage` (ChatGPT API path style). This is a
  single HTTP GET, **not a model turn**.
  [account_processor.rs](https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/account_processor.rs),
  [rate_limit_resets.rs](https://github.com/openai/codex/blob/main/codex-rs/backend-client/src/client/rate_limit_resets.rs)
- The server can also push updates unprompted: `AccountRateLimitsUpdatedNotification`
  exists as a server-to-client notification type, for clients that stay
  connected to the daemon.
  [AccountRateLimitsUpdatedNotification.ts](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/AccountRateLimitsUpdatedNotification.ts)
- There is no plain CLI subcommand for this — `codex debug --help` only
  offers `models`, `app-server`, `prompt-input` (checked directly, version
  0.154.0); `codex account --help` doesn't exist as a top-level command
  either. Reaching `account/rateLimits/read` means running
  `codex app-server` (or `codex app-server proxy` against the shared daemon
  socket) and speaking JSON-RPC: send `initialize`, then the request. No
  ready-made one-liner exists upstream.
- `codex exec --json` streams the same `token_count` event (with
  `rate_limits` embedded) that lands in the rollout file, but — per
  `TokenCountEvent` in `codex-rs/protocol/src/protocol.rs` and its emission
  sites in `codex-rs/core/src/session/mod.rs` — it is only emitted as part
  of a turn's event stream, so it still costs a real turn. `/status` in the
  TUI reads the same in-memory snapshot the session already holds (updated
  after each turn), not a fresh fetch.
- **Bottom line for Q2**: yes, a read-only path exists
  (`account/rateLimits/read` over the app-server), but it requires speaking
  JSON-RPC to a running/spawned `app-server` process, not a single shell
  command.

## 3. What other people's tools do

- Rollout-file readers (same source and shape as ours):
  - **muxa** (Rust, `Open330/muxa`) —
    `crates/muxa/src/adapters/codex_rollout.rs` tails the newest rollout
    file (256 KB tail, same budget our helper uses), parses `token_count`
    events for `primary`/`secondary` `used_percent`/`resets_at`, treats a
    `credits` object going non-null as "out of rolling-window quota," and
    documents itself as "an unofficial on-disk format read best-effort" —
    explicitly modeled on Claude Code's own on-disk transcript parsing.
    [codex_rollout.rs](https://github.com/Open330/muxa/blob/main/crates/muxa/src/adapters/codex_rollout.rs)
  - **Fishbowl** (`zonion088-design/fishbowl`) — same rollout directory,
    same fragility, written up in
    [GitHub Discussion #45392](https://github.com/openai/codex/discussions/45392):
    partial trailing lines from concurrent writes, occasional corrupted
    records (references issue #45150), silent field-vocabulary changes
    across CLI versions (references issue #43593), and no reset-marker or
    stable record ID to key on.
  - Several more thin scripts of the same shape turned up in `gh search
    code` (`onewesong/codex-usage-ui`, `huytrinhm/codex-usage`,
    `insv23/dotfiles/herdr/host-status.sh`,
    `vasilyu1983/AI-Agents-public/.../codex-usage.py`, etc.) — all read
    `~/.codex/sessions/**/rollout-*.jsonl` for token/usage reporting;
    none of the ones inspected use the app-server path.
- App-server reader: **CodexFuse** (Windows tray,
  [Discussion #45699](https://github.com/openai/codex/discussions/45699))
  polls `account/rateLimits/read` directly and shows the exact reset-window
  ambiguities (`secondary: null`, `windowDurationMins: 10080` for
  weekly-only plans) that a rollout-file reader would also have to handle.
  Its author's framing — "polls the same App Server path Codex uses" — is
  independent confirmation the method is real and reachable outside the
  Codex binary itself.

## 4. Staleness / refreshing without a full model turn

- Our own test (`codex exec` with a trivial prompt, killed after >120s) hit
  cold-start cost because `exec` always spins up a full session (model
  auth, sandbox, context) before it can emit even one `token_count` event —
  there is no "cheap ping" mode for `exec`.
- `account/rateLimits/read` is the cheap alternative: it's a single GET to
  `/api/codex/usage` with no model call, so it can be polled on demand
  without waiting on a turn. The cost is process/protocol overhead — you
  need a running `app-server` (or `app-server proxy` against
  `$CODEX_HOME/app-server-control/app-server-control.sock` if one is
  already up from another client) and a completed `initialize` handshake
  before the request is accepted.
- No documented lower-level primitive (bare auth ping, HEAD request) beyond
  that GET was found in the source or docs.

## Options for our helper, ranked

1. **Keep reading the rollout JSONL (current approach), but treat it as
   explicitly non-durable.** Cheapest, zero extra process, matches what
   most third-party tools do — but OpenAI's own maintainer said plainly in
   [issue #43593](https://github.com/openai/codex/issues/43593#issuecomment)
   / the linked #45251 answer: "Interfaces and features that are meant to
   be durable (like the app server API) are documented as such. For
   everything else, it's best to assume that it's not durable or
   guaranteed." Rollout files are in the "everything else" bucket. Keep the
   current tail-and-fail-soft design (already does this well: `find()`
   walks the decoded event rather than assuming exact structure, and prints
   nothing rather than a stale/wrong number), but don't expect the shape to
   hold across CLI upgrades without a version check.
2. **Switch to `account/rateLimits/read` via `codex app-server`.** More
   robust per OpenAI's own durability statement and confirmed independently
   by a third-party tool (CodexFuse) using it in production. Cost: have to
   spawn/attach to an `app-server` process, speak the JSONL-framed
   `initialize` → `account/rateLimits/read` handshake, and manage that
   process's lifecycle (or find and reuse the shared daemon socket, if the
   installed CLI version exposes one — `codex app-server proxy` implies one
   exists at `$CODEX_HOME/app-server-control/app-server-control.sock`).
   This is real integration work, not a drop-in swap for a Python script
   tailing a file.
3. **Hybrid**: keep the rollout-tail as the fast path (it's already
   read-only, sub-millisecond, no process spawn) and fall back to
   `account/rateLimits/read` only when the rollout read is stale beyond the
   helper's existing `STALE_AFTER` threshold, or when the shape check
   (`find()` returning `None`) fails outright — i.e., detect drift instead
   of trusting the file blindly. This keeps today's near-zero cost for the
   common case while giving a real fallback instead of just printing `?`
   forever after a CLI upgrade changes the wire shape.

Evidence is solid for what's on disk today and for the existence and
mechanics of `account/rateLimits/read`. Evidence is thinner on exactly how
cheap/simple it would be to reuse an *already-running* app-server daemon
from a short-lived helper script versus spawning a fresh one each poll —
that would need a short spike against the local socket to measure real
per-call latency before committing to option 2 or 3.
