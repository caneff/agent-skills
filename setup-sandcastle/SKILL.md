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

The [`install`](install) script does the whole install and owns every prereq
check, every command and every message. You own three things: proposing the
language arm, the human half of `.env`, and reading a failure.

## Ask which arm this repo is

The script takes the arm as a required positional and **never infers it** — a
wrong inference would render a Python sandbox over a Node repo. Propose from
what the target carries and let the user answer:

- a `.python-version` or a `pyproject.toml` → propose `python`
- a `package.json` and no Python marker → propose `node`

## Run it

From the **root of the target repo**, invoked by path out of this skill:

```
<skills-repo>/setup-sandcastle/install <python|node> [--preflight] [--env-from <path>]
```

`--preflight` runs the checking phase and stops, mutating nothing — use it to
tell a user whether their repo is ready without committing to an install.
`--env-from` takes a path to an existing `.env` to copy in; ask for one before
you run (see below), and omit the flag if the user has not got the values yet.
A full run repeats every preflight check, so there is no need to run both.

Sandcastle consumes a gate command, PR CI, `CODING_STANDARDS.md` and
`AGENTS.md`, and creates none of them. Preflight fails on whichever is absent
and its message names the fix — on the Python arm that fix is usually
[`/setup-python-repo`](../setup-python-repo/SKILL.md), which writes all three.
A Node adopter has no equivalent skill, so there the check is the whole
obligation: nothing creates the scripts it asks for.

## What the script does

Preflight checks every prereq for the named arm and writes nothing. Then the
mutating phase runs five announced steps:

1. Render `.sandcastle/` with copier, at the newest `sandcastle-template/v*`
   tag, plus the root `.copier-answers.yml` breadcrumb.
2. Write the implementer's root `CLAUDE.md`.
3. Wire the host runtime into `package.json` and install its dependencies.
4. Copy in `.sandcastle/.env`, when `--env-from` gave a source.
5. Typecheck the rendered orchestrator with `npx tsc`.

A successful run prints what remains for a human.

## The human half of `.env`

`.sandcastle/.env` holds the Claude + GitHub tokens. **Never read it** — the
script copies by path precisely so secrets stay out of your transcript, and
`cat`ting the file to check your work would undo that.

Ask before installing: *"Seed `.sandcastle/.env` from an existing one? Give me
a path, or fill it by hand afterwards."* A path becomes `--env-from`; no path
means the script leaves the file to the user and says so on the way out.

**Then walk the user through granting the bot access to THIS repo.** A seeded
`.env` almost always carries `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY`, and
those credentials are account-level: nothing in the file changes, including
`GITHUB_APP_INSTALLATION_ID` for a same-owner repo, and
`CLAUDE_CODE_OAUTH_TOKEN` is account-level too. What is missing is this repo in
the App's existing installation. Only a human can add it:
<https://github.com/settings/installations> → the bot App → **Configure** →
**Repository access** → *Only select repositories* → add this repo → **Save**.
[`.sandcastle/bot-setup.md`](templates/.sandcastle/bot-setup.md) step 3 covers
it, and is also where an optional bot identity is set up at all.

*Fallback — PAT mode*, where the `.env` sets `GH_TOKEN` instead of the
`GITHUB_APP_*` block: a fine-grained PAT is repo-scoped, so the user mints a
fresh one for this repo at
<https://github.com/settings/personal-access-tokens/new> (Issues R/W, Pull
requests R/W, Contents R/W, Metadata R) and replaces `GH_TOKEN`.

## How to read a failure

Every failure exits the same non-zero status and the message names the step, so
the judgement is yours. Three classes:

- **Preflight refused.** Nothing was mutated — that is preflight's whole
  guarantee. Fix what the message names and re-run the same command. Always
  safe.
- **A mutating step failed.** The `CLAUDE.md` write, the host-runtime wiring and
  the `.env` copy are all idempotent, so re-running is safe. **The render is
  not**, and preflight now refuses a second run over an existing render. So a
  failure at step 1 means: read `git status` in the target, decide by hand, and
  do not re-run blindly.
- **The typecheck failed.** The install landed, but the rendered orchestrator
  does not typecheck against the pinned library. That is a **template bug, not
  an install failure** — report it against the skills repo. Nothing you do in
  the target repo will fix it, so do not retry.

## Updating adopters

Installed repos receive later `sandcastle-template/vN` tags through the
[`sandcastle-propagate`](sandcastle-propagate) sweep — runbook in
[`references/updating-adopters.md`](references/updating-adopters.md), reasoning
in [`references/design-decisions.md`](references/design-decisions.md).
