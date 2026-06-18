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
4. **Auto-detects which skills you've edited** and protects them: for each lock-tracked skill it compares your pre-update tree SHA to the lock's `skillFolderHash`; any that diverged are ones you changed. If upstream also changed such a skill, it **restores your version** and prints `git diff PRE POST -- <skill>` so you can review the upstream delta and merge by hand.
5. Prints a change summary and the one-line undo: `git reset --hard PRE`.

Unedited skills update normally. Nothing is ever lost — `PRE` is always in git.

## Why auto-detect (not a pre-edit prompt)

"Protect a skill when I edit it" is tempting to wire as a hook on Edit/Write, but it's unnecessary: a skill *is* edited exactly when its content diverges from the lock's recorded upstream hash. Detecting that at update time needs no list, no event hook, and can't be forgotten. Edit freely; protection is computed for you.

## Optional manual override

If you want to force-protect a skill the auto-detector can't see (e.g. a hand-made skill with no lockfile entry), create `.protected-skills` at the skills-dir root — one skill name per line, `#` comments allowed. It's unioned with the auto-detected set. Most setups never need it.

## Notes

- This skill is hand-maintained, not installed via `npx skills`, so it has no lockfile entry and the package manager leaves it alone.
- After a clean review, you're already committed — the git buffer stays current for next time.
- Lockfile drift (entries for deleted skills, or skills you added by hand) is a separate one-time cleanup, not handled here: drop dead entries and add untracked ones in `~/.agents/.skill-lock.json`.
