---
name: setup-sandcastle
description: Install the Sandcastle dev-automation orchestrator into a Python repo that already ran setup-python-repo. Adds .sandcastle/ (a plan→implement→review→PR agent pipeline over GitHub issues), wires it to `just check`, and runs agents in isolated Docker sandboxes. Requires Docker + a Node host runtime + the tdd skill.
disable-model-invocation: true
---

# Install Sandcastle into a Python repo

Bolt the **Sandcastle** orchestrator onto a repo so AFK agents turn
`ready-for-agent` GitHub issues into reviewed PRs. `main.mts` loops
plan→execute over issues; per issue an **implementer** agent makes commits and
runs `just check`, then a **reviewer** agent gates the branch against the issue
spec; completed issues open one PR per dependency component.

This composes **on top of** [`setup-python-repo`](../setup-python-repo/SKILL.md):
it consumes that repo's `just check`, PR CI, `CODING_STANDARDS.md`, and
`AGENTS.md`. It does not create them — **step 0 hard-requires them.**

The orchestrator lives in this skill's [`templates/`](templates/) as a **copier
template** (the canonical home where the `.mts` is hacked with its vitest suite
green). Targets get **runtime-only** code — no tests, no vitest. Install
**renders** it with copier: prompts/config already ship Python-retargeted, and
the one interpreter-specific value — `PYTHON_VERSION` — copier fills from the
target's `.python-version` (no install-time `sed`).

## 0. Prereqs — check, fail fast

Abort with the exact fix if any is missing:

- **setup-python-repo markers** — `just --list` shows a `check` recipe; a PR CI
  workflow exists (`.github/workflows/*.yml`); `CODING_STANDARDS.md` and
  `AGENTS.md` are present. Missing → *"run `/setup-python-repo` first."*
- **tdd skill** — `~/.claude/skills/tdd/` exists (the implementer prompt calls
  `/tdd`; step 3 mounts your global skills into the sandbox). Missing →
  *"install the tdd skill first."*
- **Docker** — `docker info` succeeds (agents run in Docker sandboxes).
- **Node host runtime** — `node` and `npx` on PATH (`main.mts` runs on the host
  via tsx). No Node in the sandbox image — only on the host.
- **copier** — `command -v copier` (the template engine step 1 renders with;
  `uv tool install copier` if missing).
- Target is a git repo with `.python-version`.

**Done when:** all six pass, or you've stopped with the precise missing-prereq message.

## 1. Render the orchestrator with copier

`copier copy` renders the template into `.sandcastle/`: it drops the dev-only
`tests/` (a target never edits the `.mts`), fills `PYTHON_VERSION` into the
Dockerfile from the target's `.python-version`, and writes
`.sandcastle/.copier-answers.yml` — the breadcrumb recording the template
version (`_commit`) this repo sits on, so a later `copier update` can merge in
template edits. Source the **skills repo**, not the template subfolder — copier
records `_commit` only from the git root (why: `references/design-decisions.md`
decision 4). It emits the subtree at the destination root, so render into
`./.sandcastle`:

```bash
copier copy --defaults \
  --vcs-ref=sandcastle-template/v1 \
  --data PYTHON_VERSION="$(cat .python-version)" \
  https://github.com/caneff/agent-skills.git ./.sandcastle
```

`--vcs-ref` pins to the current template tag — bump it whenever a newer
`sandcastle-template/vN` ships. (A local checkout path — the skills repo root —
works too and needs no network, but records a machine-local `_src_path`.)

**Done when:** `.sandcastle/main.mts` exists, `.sandcastle/tests/` does not, the
Dockerfile's `ARG PYTHON_VERSION` equals `.python-version`, and
`.sandcastle/.copier-answers.yml` is present.

## 2. Wire the host runtime (package.json)

`main.mts` runs on the host via tsx and imports `@ai-hero/sandcastle` + `zod`.
`npm init -y` if there's no `package.json`, then set deps + the run script
(idempotent — works empty or populated):

```bash
[ -f package.json ] || npm init -y
npm pkg set 'dependencies.@ai-hero/sandcastle=0.10.0'   # EXACT pin — upstream drift is deliberate
npm pkg set 'dependencies.zod=^4.4.3'
npm pkg set 'dependencies.@standard-schema/spec=^1.0.0'  # sandcastle's .d.ts imports it but doesn't declare it — without this the Output.object<T> generic collapses to any
npm pkg set 'devDependencies.tsx=^4.19.0'
npm pkg set 'devDependencies.typescript=^5.6.0'
npm pkg set 'devDependencies.@types/node=^22.0.0'        # tsconfig sets types:["node"]; tsc fails without it
npm pkg set 'scripts.sandcastle=npx tsx .sandcastle/main.mts'
npm install
```

Add `node_modules/` to the repo's `.gitignore` if it isn't already ignored.

**Done when:** `npm ls @ai-hero/sandcastle` shows `0.10.0`.

## 3. Seed `.env` (careful — secrets path)

`.sandcastle/.env` holds the Claude + GitHub tokens. **Copy by path, never read
its contents** — reading a filled `.env` would pull secrets into the transcript.

Ask: *"Seed `.sandcastle/.env` from an existing one? Give a path, or skip to
fill by hand."*

- **Path given:**
  1. `cp <path> .sandcastle/.env` — shell only; do not `cat`/`echo`/`Read` it.
  2. Ensure the copy is gitignored: `.sandcastle/.gitignore` already lists
     `.env`; if `git check-ignore .sandcastle/.env` does **not** report it,
     create/append the `.gitignore` so it is.
  3. `git check-ignore .sandcastle/.env` must confirm ignored, else **abort +
     warn** (never leave a stageable `.env`).
  4. **Grant the GitHub-App bot access to THIS repo** (the default / expected
     path — the `.env` almost always carries `GITHUB_APP_ID` +
     `GITHUB_APP_PRIVATE_KEY`). The App credentials are account-level and do
     **not** change; you only add this repo to the App's existing installation.
     The skill never reads the `.env`, so **print** these instructions:
     - No `.env` edits needed. `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, and
       (for a same-owner repo) `GITHUB_APP_INSTALLATION_ID` all stay as seeded.
     - Add the repo to the installation:
       <https://github.com/settings/installations> → the bot App → **Configure**
       → **Repository access** → *Only select repositories* → add THIS repo →
       **Save**. See [`.sandcastle/bot-setup.md`](templates/.sandcastle/bot-setup.md) Step 3.
     - `CLAUDE_CODE_OAUTH_TOKEN` is account-level — unchanged.
     - Verify (user runs it — prints a token, keep it out of the transcript):
       `set -a; . .sandcastle/.env; set +a; GH_TOKEN=$(node .sandcastle/mint-gh-token.mjs) gh api repos/<owner>/<repo> --jq .full_name`
       — should echo the repo slug.

     *Fallback — PAT mode (`GH_TOKEN` set instead of `GITHUB_APP_*`):* a
     fine-grained PAT is repo-scoped, so mint a new one for THIS repo at
     <https://github.com/settings/personal-access-tokens/new> (Issues R/W, Pull
     requests R/W, Contents R/W, Metadata R) and replace `GH_TOKEN`.
- **Skip:** `cp .sandcastle/.env.example .sandcastle/.env`; print the keys to
  fill (`CLAUDE_CODE_OAUTH_TOKEN`, `GH_TOKEN`; bot block optional).

**Done when:** `.sandcastle/.env` exists **and** `git check-ignore` confirms it's ignored.

## 4. Verify

```bash
npx tsc -p .sandcastle/tsconfig.json      # orchestrator typechecks against the installed lib
```

A clean typecheck proves the deps resolved and `main.mts` is compatible with the
pinned `@ai-hero/sandcastle`. Fix anything red before declaring done.

**Done when:** `npx tsc -p .sandcastle/tsconfig.json` exits clean.

## Notes — what the user does next (not the skill's job)

- **Fill `.env`** (if skipped in step 3), then build the sandbox image via the
  sandcastle CLI, then `npm run sandcastle`.
- **Label issues `ready-for-agent`** — the planner only selects those.
- **Optional bot identity** — see [`.sandcastle/bot-setup.md`](templates/.sandcastle/bot-setup.md)
  to attribute PRs to a GitHub App instead of your account. Off until the
  `GITHUB_APP_*` env vars are set.
- **Upstream upgrades** are a *maintenance* action on this skill's `templates/`,
  not on a target. In `templates/`: `npm outdated @ai-hero/sandcastle` → read
  its CHANGELOG → bump the pin → `npm run typecheck && npm test` → commit. The
  next install carries it. **This skill is install-only** — it does not update an
  already-installed `.sandcastle/`.
