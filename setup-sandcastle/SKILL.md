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
copier fills the answers — `LANGUAGE`, which defaults to `python`, and (for a
Python adopter) `PYTHON_VERSION` from the target's `.python-version` — with no
install-time `sed`.

## 0. Prereqs — check, fail fast

Abort with the exact fix if any is missing:

- **setup-python-repo markers** — `just --list` shows a `check` recipe; a PR CI
  workflow exists (`.github/workflows/*.yml`); `CODING_STANDARDS.md` and
  `AGENTS.md` are present. Missing → *"run `/setup-python-repo` first."*
- **tdd skill** — `~/.claude/skills/tdd/` exists (the implementer prompt calls
  `/tdd`; the sandbox bind-mounts `~/.claude/skills` at run time, so it resolves
  in-container). Missing → *"install the tdd skill first."*
- **Docker** — `docker info` succeeds (agents run in Docker sandboxes).
- **Node host runtime** — `node` and `npx` on PATH (`main.mts` runs on the host
  via tsx). No Node in the sandbox image — only on the host.
- **copier** — `command -v copier` (the template engine step 1 renders with;
  `uv tool install copier` if missing).
- Target is a git repo with `.python-version`.

**Done when:** all six pass, or you've stopped with the precise missing-prereq message.

## 1. Render the orchestrator with copier

`copier copy` renders the template as a `.sandcastle/` **subtree at this repo's
root**: it drops the dev-only `tests/` (a target never edits the `.mts`), fills
`PYTHON_VERSION` into the Dockerfile from the target's `.python-version`, and
writes a root `.copier-answers.yml` — the breadcrumb recording the template
version (`_commit`) this repo sits on, so a later `copier update` can merge in
template edits. Source the **skills repo**, not the template subfolder — copier
records `_commit` only from the git root (why: `references/design-decisions.md`
decision 4). The subproject root **is** this repo's git root (#93), so render
into `.` — copier writes only `.sandcastle/` and the root breadcrumb, scattering
nothing else across the target:

```bash
copier copy --defaults \
  --vcs-ref=sandcastle-template/v4 \
  --data PYTHON_VERSION="$(cat .python-version)" \
  https://github.com/caneff/agent-skills.git .
```

`--vcs-ref` pins to the current template tag — bump it whenever a newer
`sandcastle-template/vN` ships. (A local checkout path — the skills repo root —
works too and needs no network, but records a machine-local `_src_path`.)

**Done when:** `.sandcastle/main.mts` exists, `.sandcastle/tests/` does not, the
Dockerfile's `ARG PYTHON_VERSION` equals `.python-version`, and a root
`.copier-answers.yml` is present.

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

Once a repo is installed, later `sandcastle-template/vN` tags reach it through
the [`sandcastle-propagate`](sandcastle-propagate) maintainer script. It
discovers every adopter under `~/src` by its root `.copier-answers.yml`
breadcrumb (no hardcoded list), preserves each repo's `PYTHON_VERSION`, then
commits `.sandcastle` and pushes. Always dry-run first:

```bash
sandcastle-propagate --dry-run     # show what each repo would receive
sandcastle-propagate               # copier update, commit, push (skips dirty repos)
```

Pass a ref to pin (`sandcastle-propagate sandcastle-template/v4`); the default
is the newest `sandcastle-template/v*` tag.

**Install it as a symlink, never a copy**
(`ln -sf "$PWD/setup-sandcastle/sandcastle-propagate" ~/.local/bin/`). A copy goes
stale, and a stale copy fails *silently*: the pre-#93 version searched
`*/.sandcastle/.copier-answers.yml`, so once adopters moved their breadcrumb to
the repo root it reported `updated=0 skipped=0` — indistinguishable from "every
repo is already current" while it swept past all of them.

**It is a real 3-way merge, not a re-render.** The script runs `copier update`
(#93): template edits merge in and a file an adopter legitimately edited under
`.sandcastle` is preserved. Update resolves now because the subproject root is
the repo's git root, so copier's update diff runs against a path that exists in
both the temp render and the real tree. A genuine conflict (adopter and template
touched the same lines) lands as inline `<<<<<<<` markers; the script refuses to
commit such a tree and flags the repo for a human, so a half-merged state is
never pushed.

Safety properties:

- **Runtime state is untouched.** `.env`, `logs/`, `worktrees/`, and
  `review-attempts.json` are not template-rendered, so copier never writes or
  deletes them.
- **Uncommitted work is skipped.** The script refuses any repo with a dirty
  tree — commit or stash first. On a clean repo it commits `.sandcastle` and the
  root breadcrumb before pushing, so every merged change is in that commit's
  diff.

To confirm before running, `--dry-run` (`copier update --pretend`) shows the
merge each repo would receive without touching it.

### One-time migration off the old layout

Repos installed before #93 carry the breadcrumb at `.sandcastle/.copier-answers.yml`
(the old `./.sandcastle` subdir layout) and are pinned to a pre-v4 tag. `copier
update` cannot bridge that layout shift — the old ref renders its files at the
root the new one puts under `.sandcastle/`, so the update diff sees every file
move — so migrate each once, by hand.

**Migrate by MERGING, never by re-rendering.** A `copier copy --overwrite` is the
obvious shortcut and it is wrong: it replaces every file an adopter edited with
template text, and it does so silently, since copier prints `overwrite` for a
clobbered local edit and a stale template file alike. This documentation used to
recommend that shortcut on the grounds that `.sandcastle` is "generated and
unedited". **It isn't.** visual-teach carried a hand-edited `Dockerfile`, a TS
sandbox bootstrap (`npm install` in place of `uv sync`), and its own prompt-drawer
wording; the re-render took all of it, and none of those files had even changed
between the adopter's pinned tag and the target one. Assume every adopter has
edits until you have diffed and proved otherwise.

Do a real 3-way merge instead. Render both refs, then merge per file with
`git merge-file`: base = the OLD ref's render, ours = the repo as it stands,
theirs = the NEW ref's render.

```bash
# from the adopter repo root, on a clean tree, on a fresh branch:
OLD=$(sed -n 's/^_commit: *//p' .sandcastle/.copier-answers.yml)
NEW=sandcastle-template/v5
PYV=$(sed -n 's/^PYTHON_VERSION: *//p' .sandcastle/.copier-answers.yml | tr -d "\"'")
URL=https://github.com/caneff/agent-skills.git

copier copy --defaults --trust --vcs-ref="$OLD" --data PYTHON_VERSION="$PYV" "$URL" /tmp/base
copier copy --defaults --trust --vcs-ref="$NEW" --data PYTHON_VERSION="$PYV" "$URL" /tmp/new

# OLD renders at /tmp/base root (subdir layout); NEW renders under /tmp/new/.sandcastle.
cd /tmp/new/.sandcastle && find . -type f | sed 's|^\./||' | while read -r f; do
  ours="$REPO/.sandcastle/$f"
  [ -f "$ours" ] || { mkdir -p "$(dirname "$ours")"; cp "$f" "$ours"; continue; }   # new file
  git merge-file -L ours -L base -L theirs "$ours" "/tmp/base/$f" "$f" || echo "CONFLICT $f"
done

cp /tmp/new/.copier-answers.yml "$REPO/.copier-answers.yml"   # breadcrumb moves to the root
git -C "$REPO" rm -q .sandcastle/.copier-answers.yml
```

**A line merge is not enough for a badly diverged file.** `git merge-file` works a
region at a time, so on a file that drifted far it happily keeps *ours* where the
new version added a definition and *theirs* where the new version calls it — a
result that is textually merged and semantically broken. That is not a
hypothetical: migrating visual-teach this way produced a `main.mts` calling
`parseCheckVerdict` and `retiredByGate` that nothing defined, and a `reconcile.mts`
missing the very buckets `main.mts` passed it.

So split the files by how far they drifted:

- **A file with a handful of deliberate local edits** — take the NEW render whole
  and re-apply those edits by hand, each with a comment naming why it diverges.
  Cleaner than any merge, and the next `copier update` conflict reads clearly.
- **A file whose local side is only pre-old-ref template text** (an adopter pinned
  to a tag its files predate — common) — take the new render whole. Prove it first
  by finding the same lines in an older render, not by eye.
- **A file the template never changed between the two refs** — leave it entirely
  alone. Diff the two renders and you will usually find most files are in this
  bucket, which is exactly why re-rendering costs so much for so little.

Then, before committing:

1. **Resolve every conflict by reading it.** A conflict whose local side is empty
   is a template addition — take theirs. A conflict with real local content is a
   decision; make it deliberately.
2. **Prove no local line vanished.** For each file, extract the lines the repo had
   that the OLD render did not — those are its edits — and confirm each one is
   still present in the merged file. That check is what catches a silent clobber.
   Then classify each line it flags: age, or customization? Only the second kind
   is a loss.
3. **Re-apply any divergence the merge could not keep**, with a comment saying why,
   so the next `copier update` conflict is legible instead of mysterious.
4. **Refresh `.sandcastle/tests/` too.** Adopters carry copies of the dev-home
   suite, and copier excludes tests from the render, so they never update
   themselves — they will be pinned to whatever API the adopter installed. Copy
   the current suite over (skip `copier-template.test.mjs`, which tests this skill,
   not a target), and locally adapt any assertion that encodes a local divergence.
5. **Run the adopter's whole CI locally, and read the EXIT CODE.** Not just
   `tsc` — whatever its workflow runs, typically `npm run lint && npm run typecheck
   && npm test`. Check `$?` explicitly; a wrapper or a summarizing proxy can print
   something that reads like success over a failing command, and the migration that
   prompted this rule was pushed on exactly that false green.
6. **Open a PR.** A migration is not an auto-ship: a human reads what moved.

After that one migration, `sandcastle-propagate` (real `copier update`) carries
every future tag.

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
