---
name: sandcastle-codex
description: Use a Codex/ChatGPT subscription (not an OpenAI API key) when running Sandcastle's Codex agent in a sandbox. Use when the user wants Sandcastle's codex agent to authenticate with their ChatGPT/Codex subscription, mentions subscription/ChatGPT auth for Codex, wants to avoid an OPENAI_API_KEY, or hits "Quota exceeded" running Codex in a Sandcastle sandbox.
disable-model-invocation: true
---

# Sandcastle Codex — use a subscription instead of an API key

Make Sandcastle's **codex agent** authenticate with the user's **ChatGPT/Codex
subscription** instead of an OpenAI Platform API key.

On current Sandcastle this needs **no workarounds** — just bind-mount the host's
Codex auth into the sandbox and make sure no API key is set. (Earlier this skill
shipped an auth-staging cache + an extended Docker image; both are obsolete since
Sandcastle ≥ 0.5.10 fixed single-file bind-mount permissions — commit `9bf43df`.)

## How Codex auth works here

- `codex login` writes `~/.codex/auth.json` with `auth_mode: "chatgpt"` — these are
  subscription tokens, not an API key.
- Inside the sandbox the codex CLI reads `~/.codex/auth.json` (i.e.
  `/home/agent/.codex/auth.json`). If that file isn't there, codex falls back to an
  API key from the env — which bills the Platform API and causes `Quota exceeded`.
- So: get `auth.json` into the sandbox, and keep every API-key env var unset.

## Setup

1. **Confirm the image has the codex CLI.** It does automatically if the project
   was `sandcastle init`'d with the **codex** agent (its Dockerfile runs
   `npm install -g @openai/codex`). If the repo used another agent, either re-init
   with codex or add that `RUN` line (before the `USER` line) to
   `.sandcastle/Dockerfile`, then `pnpm sandcastle docker build-image`.

2. **Confirm the host login** is a subscription, not a key:
   ```bash
   grep -q '"auth_mode": *"chatgpt"' ~/.codex/auth.json && echo OK || echo "run: codex login"
   ```

3. **Mount the auth into the sandbox.** In the `docker()` (or `podman()`) call of
   your `run()` entrypoint (`.sandcastle/main.ts`, or a custom script):
   ```ts
   sandbox: docker({
     mounts: [
       { hostPath: "~/.codex/auth.json", sandboxPath: "/home/agent/.codex/auth.json" },
     ],
   }),
   ```
   Sandcastle ≥ 0.5.10 auto-creates and `chown`s `/home/agent/.codex` for this
   single-file mount, so it works even on a non-codex base image. The mount is
   read-only, which is fine — subscription tokens stay valid well beyond one run.
   (Mount read-write only if you want codex to persist a refreshed token back to
   the host file.)

4. **Keep all API keys unset.** No `OPENAI_KEY` / `OPENAI_API_KEY` /
   `CODEX_API_KEY` in `.sandcastle/.env` or the inherited environment — any one of
   them overrides subscription auth and triggers Platform-API billing.

## Verify

```bash
npx tsx .sandcastle/main.ts        # or your run script
```
A normal agent response (not an auth/quota error) confirms it. For a fast check,
point the run at a trivial prompt first.

## Troubleshooting

- **`Quota exceeded. Check your plan and billing details.`** — an API key is
  leaking into the sandbox, so codex bills the Platform API. Unset
  `OPENAI_KEY`/`OPENAI_API_KEY`/`CODEX_API_KEY` (check `.sandcastle/.env` and the
  shell env) and re-run.
- **`codex: not found` (exit 127)** — the image lacks the codex CLI; see step 1.
- **Auth/permission errors on `/home/agent/.codex`** — you're on Sandcastle
  < 0.5.10. Upgrade (`pnpm add -D -w @ai-hero/sandcastle@latest`); older versions
  mount the parent dir as `root:root` and break the agent.
- **`No ~/.codex/auth.json`** — not logged in; run `codex login`.

## Version notes

Verified against `@ai-hero/sandcastle` 0.7.0 (repo: github.com/mattpocock/sandcastle).
Load-bearing facts: codex agent reads `~/.codex/auth.json`; `init --agent codex`
installs the codex CLI in the image; single-file mounts under `/home/agent` get
their parent auto-created + chowned (since 0.5.10). There is no native config/CLI
flag for subscription auth — the mount in the `run()` script is the mechanism.
