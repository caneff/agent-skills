---
name: skills-safe-update
description: Update agent skills installed via the `npx skills` package manager without losing local edits. A git buffer makes every update reviewable and reversible, and skills listed in .protected-skills keep their customizations instead of being silently overwritten. Use when the user wants to update/refresh their installed skills, pull the latest skill versions, or safely run `npx skills update` while preserving hand-edited skills.
disable-model-invocation: true
---

# Safe skills update

`npx skills update` overwrites locally-edited skills — its lockfile records only the *upstream* version (`skillFolderHash`), never your changes. This skill wraps it so edits survive.

## Quick start

```bash
bash scripts/safe-update.sh
```

Runs against `~/.agents/skills` (override with `SKILLS_DIR=...`).

## What it does

1. Ensures the skills dir is a git repo; commits a **pre-update snapshot** (`PRE`).
2. Runs `npx skills update -g`.
3. Commits the upstream result (`POST`) — so both your version and upstream's now live in git history.
4. For every skill in `.protected-skills`: if upstream changed it, **restores your version** and prints the exact `git diff PRE POST -- <skill>` to review the upstream delta and merge by hand.
5. Prints a change summary and the one-line undo: `git reset --hard PRE`.

Unprotected skills update normally. Nothing is ever lost — `PRE` is always in git.

## .protected-skills

A newline-delimited list (next to this dir, at the skills-dir root) of skill folders you've hand-edited. `#` comments allowed. Example:

```
teach
implement-paper
marimo-notebook
```

Add a skill here the moment you edit it, so the next update preserves it.

## Notes

- This skill is hand-maintained, not installed via `npx skills`, so it has no lockfile entry and the package manager leaves it alone.
- After a clean review, you're already committed — the git buffer stays current for next time.
- Lockfile drift (entries for deleted skills, or skills you added by hand) is a separate one-time cleanup, not handled here: drop dead entries and add untracked ones in `~/.agents/.skill-lock.json`.
