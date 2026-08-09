---
name: setup-sandcastle
description: Install the Sandcastle dev-automation orchestrator into a repo. Adds .sandcastle/ (a plan→implement→review→PR agent pipeline over GitHub issues), wires it to the repo's own gate command, and runs agents in isolated Docker sandboxes. Requires Docker + a Node host runtime + the tdd skill.
disable-model-invocation: true
---

# Install Sandcastle into a repo

Bolt the **Sandcastle** orchestrator onto a repo so AFK agents turn
`ready-for-agent` GitHub issues into reviewed PRs. `main.mts` loops
plan→execute over issues; per issue an **implementer** agent makes commits and
runs the repo's gate, then a **reviewer** agent gates the branch against the
issue spec; completed issues open one PR per dependency component.

It consumes a gate command, PR CI, `CODING_STANDARDS.md`, and `AGENTS.md`, and
creates none of them — **step 0 hard-requires them.** On the Python arm those
come from [`setup-python-repo`](../setup-python-repo/SKILL.md), which the gate
below names as the fix. A Node adopter has no equivalent skill to lean on, so
step 0's assertion **is** the whole obligation: nothing creates the scripts it
checks for.

The orchestrator lives in this skill's [`templates/`](templates/) as a **copier
template** (the canonical home where the `.mts` is hacked with its vitest suite
green). Targets get **runtime-only** code — no tests, no vitest. Install
**renders** it with copier, which fills the answers — `LANGUAGE`, which
defaults to `python`, and (for a Python adopter) `PYTHON_VERSION` from the
target's `.python-version` — with no install-time `sed`.

## 0. Prereqs — check, fail fast

**Establish `LANGUAGE` before checking anything language-specific.** Ask the
user which arm this repo is — `python` or `node` — proposing what the target
suggests (a `.python-version` or `pyproject.toml` → `python`; a `package.json`
and no Python marker → `node`). The answer picks the arm below and is the same
answer step 1 passes to copier.

Then abort with the exact fix if any prereq is missing.

**Both arms:**

- **tdd skill** — `~/.claude/skills/tdd/` exists (the implementer prompt calls
  `/tdd`; the sandbox bind-mounts `~/.claude/skills` at run time, so it resolves
  in-container). Missing → *"install the tdd skill first."*
- **Docker** — `docker info` succeeds (agents run in Docker sandboxes). Missing
  → *"start Docker first: agents run in Docker sandboxes."*
- **Node host runtime** — `node` and `npx` on PATH (`main.mts` runs on the host
  via tsx). The Python arm's sandbox image carries no Node; the Node arm's does,
  for the target's own toolchain, not for `main.mts`.
- **copier** — `command -v copier` (the template engine step 1 renders with;
  `uv tool install copier` if missing).
- **Target is a git repo**, with a PR CI workflow (`.github/workflows/*.yml`)
  and `CODING_STANDARDS.md` and `AGENTS.md` present — the reviewer reads the
  standards, the implementer reads `AGENTS.md`. Name whichever is absent:
  *"Sandcastle needs a PR CI workflow / `CODING_STANDARDS.md` / `AGENTS.md`;
  it consumes them and creates none of them."* On the Python arm,
  `/setup-python-repo` writes all three.

**Python arm (`LANGUAGE=python`) also:**

- **`.python-version`** at the repo root — step 1 reads it for the image's
  interpreter. Missing → *"run `/setup-python-repo` first: no `.python-version`."*
- **`just --list` shows `check`, `lint` and `typecheck`** — the render names all
  three. Name whichever is absent: *"no `just check` recipe — run
  `/setup-python-repo` first"*, *"`just` has no `lint` recipe; the per-commit
  fast check calls it"*, *"`just` has no `typecheck` recipe; the per-commit fast
  check calls it."*

The assertion reaches past `check` deliberately. A repo may define `check` as one
monolithic recipe with no separate `lint` or `typecheck`, and the implementer's
per-commit fast check would then call a recipe that does not exist.

**Node arm (`LANGUAGE=node`) also:**

- **`package.json` at the repo root** defining a `lint`, a `typecheck` and a
  `test` script — the render composes the gate from exactly those three, the way
  `just check` composes its recipes. Missing file → *"no `package.json`:
  Sandcastle's Node arm gates on npm scripts."* Missing script, named one by
  one: *"`package.json` defines no `lint` script; the gate and the per-commit
  fast check both call `npm run lint`"*, the same for `typecheck`, and
  *"`package.json` defines no `test` script; the gate calls `npm run test`"* —
  the per-commit fast check runs `npx vitest run <files>` instead, since `npm
  run test` silently drops the file arguments.

This arm's prereqs are the whole list: no `.python-version`, no
`/setup-python-repo`.

**Done when:** every shared prereq and every prereq of the established arm
passes, or you have stopped with the precise missing-prereq message.

## 1. Render the orchestrator with copier

`copier copy` renders the template as a `.sandcastle/` **subtree at this repo's
root**: it drops the dev-only `tests/` (a target never edits the `.mts`), renders
the arm `LANGUAGE` names — on the Python arm filling `PYTHON_VERSION` into the
Dockerfile from the target's `.python-version` — and writes a root
`.copier-answers.yml`, the breadcrumb recording the template
version (`_commit`) this repo sits on, so a later `copier update` can merge in
template edits. Source the **skills repo**, not the template subfolder — copier
records `_commit` only from the git root (why: `references/design-decisions.md`
decision 4). The subproject root **is** this repo's git root (#93), so render
into `.` — copier writes only `.sandcastle/` and the root breadcrumb, scattering
nothing else across the target:

```bash
# Python arm
copier copy --defaults \
  --vcs-ref=sandcastle-template/v4 \
  --data LANGUAGE=python \
  --data PYTHON_VERSION="$(cat .python-version)" \
  https://github.com/caneff/agent-skills.git .

# Node arm — no PYTHON_VERSION; copier does not ask for it on this arm
copier copy --defaults \
  --vcs-ref=sandcastle-template/v4 \
  --data LANGUAGE=node \
  https://github.com/caneff/agent-skills.git .
```

`--vcs-ref` pins to the current template tag — bump it whenever a newer
`sandcastle-template/vN` ships. (A local checkout path — the skills repo root —
works too and needs no network, but records a machine-local `_src_path`.)

**Done when:** `.sandcastle/main.mts` exists, `.sandcastle/tests/` does not, a
root `.copier-answers.yml` is present recording the `LANGUAGE` you chose, and —
on the Python arm — the Dockerfile's `ARG PYTHON_VERSION` equals
`.python-version`.

## 2. Seed the implementer's `CLAUDE.md`

Headless `claude` auto-loads a repo-root `CLAUDE.md` and expands its
`@`-imports, but it ignores `AGENTS.md` on its own — so without this file the
implementer builds blind and the coding standard reaches only the review gate.
Seed a root `CLAUDE.md` whose whole body is the two imports (step 0 already
required both targets, so they resolve inside the sandbox):

```bash
printf '@AGENTS.md\n@CODING_STANDARDS.md\n' > CLAUDE.md
```

The install step seeds it and copier never manages it — the template renders
only `.sandcastle/` and the root breadcrumb, never a root `CLAUDE.md`, so
`copier update` leaves it untouched. Import the **root** `CODING_STANDARDS.md`
(the src standard the implementer builds against), not the `.sandcastle/`
orchestrator standard the review gate loads conditionally.

**Done when:** `CLAUDE.md` exists at the repo root and its body is exactly
`@AGENTS.md` then `@CODING_STANDARDS.md`.

## 3. Wire the host runtime (package.json)

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

## 4. Seed `.env` (careful — secrets path)

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

## 5. Verify

```bash
npx tsc -p .sandcastle/tsconfig.json      # orchestrator typechecks against the installed lib
```

A clean typecheck proves the deps resolved and `main.mts` is compatible with the
pinned `@ai-hero/sandcastle`. Fix anything red before declaring done.

**Done when:** `npx tsc -p .sandcastle/tsconfig.json` exits clean.

## Updating adopters

Installed repos receive later `sandcastle-template/vN` tags through the
[`sandcastle-propagate`](sandcastle-propagate) sweep — runbook in
[`references/updating-adopters.md`](references/updating-adopters.md), reasoning
in [`references/design-decisions.md`](references/design-decisions.md).

## Notes — what the user does next (not the skill's job)

- **Fill `.env`** (if skipped in step 4), then build the sandbox image via the
  sandcastle CLI, then `npm run sandcastle`.
- **Label issues `ready-for-agent`** — the planner only selects those.
- **Optional bot identity** — see [`.sandcastle/bot-setup.md`](templates/.sandcastle/bot-setup.md)
  to attribute PRs to a GitHub App instead of your account. Off until the
  `GITHUB_APP_*` env vars are set.
- **Upstream upgrades** are a *maintenance* action on this skill's `templates/`,
  not on a target. In `templates/`: `npm outdated @ai-hero/sandcastle` → read
  its CHANGELOG → bump the pin → `npm run typecheck && npm test` → commit. The
  next install carries it, and `sandcastle-propagate` (see "Updating adopters")
  pushes it to repos already installed.
