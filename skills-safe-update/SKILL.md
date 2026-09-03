---
name: skills-safe-update
description: Update agent skills installed via the `npx skills` package manager without losing local edits — including following upstream renames, folder moves, and rewrites that a plain update would drop as orphans. A git buffer makes every update reviewable and reversible; edited skills keep their customizations instead of being silently overwritten; renamed/moved skills get their successors installed and edits judged (replay vs subsumed). Use when the user wants to update/refresh installed skills, pull the latest versions, safely run `npx skills update`, or reconcile a source's skills (e.g. `/skills-safe-update mattpocock`).
disable-model-invocation: true
---

# Safe skills update

`npx skills update` overwrites locally-edited skills — its lockfile records only the *upstream* version (`skillFolderHash`), never your changes. This skill wraps it so edits survive.

## Quick start

```bash
bash scripts/skills-status.sh   # read-only: what's edited vs out of date
bash scripts/safe-update.sh     # do the update, preserving edits
```

Both run against `~/.agents/skills` (override with `SKILLS_DIR=...`).

## Hand-installed skills (.extra-skills.json)

Skills not installed via `npx skills` are invisible to the lockfile. Register
them in `~/.agents/skills/.extra-skills.json` and both scripts cover them —
status rows get an `[extra]` tag, and `safe-update.sh` syncs them from their
github upstream inside the same git buffer, with the same edit protection:

```json
{ "prompt-master": { "repo": "nidhinjs/prompt-master", "path": "", "treeSha": "<tree sha of installed upstream version>" } }
```

`path` is the skill's folder inside the repo (`""` = repo root). `treeSha` is
the git tree SHA of that folder at the version you installed (get it from
`gh api repos/<repo>/commits/<ref> --jq .commit.tree.sha` for root skills);
the update script bumps it on every sync.

## Always digest the result (required)

`safe-update.sh` prints raw name-lists and a `--stat`. That is NOT the deliverable. After it finishes, **read the actual diffs and give the user a plain-English digest** — this step runs every time, not on request.

The script emits anchors on its last lines for you:

```
DIGEST_PRE=<sha>          DIGEST_POST=<sha>
DIGEST_SKILLS_DIR=<dir>   DIGEST_CHANGED=<space-separated skill names>
DIGEST_KEPT=<space-separated protected skill names>
```

Then:

1. For each changed skill, read its content diff — prose files only, skip pure boilerplate:
   ```bash
   git -C <DIGEST_SKILLS_DIR> --no-pager diff <DIGEST_PRE> <DIGEST_POST> -- <skill>/SKILL.md <skill>/*.md
   ```
2. Write the digest as a short list: **one line per skill that meaningfully changed, in plain English — what changed and why it matters**, not a file stat. Collapse repeated mechanical changes (e.g. "every skill gained an `agents/openai.yaml` OpenAI variant") into a single cross-cutting line.

## Resolve protected conflicts (required, interactive)

The protected (`DIGEST_KEPT`) skills kept YOUR version — the update reverted every upstream change to files that already existed in them (protection is whole-file, not a line-merge; only brand-new upstream files survive). Do NOT leave this as a passive "review by hand" note. For **each** kept skill:

1. Read what upstream actually changed and was dropped:
   ```bash
   git -C <DIGEST_SKILLS_DIR> --no-pager diff <DIGEST_PRE> <DIGEST_POST> -- <skill>
   ```
2. Determine whether upstream changed anything **beyond** the inverse of your local edit. If the entire `PRE..POST` diff is just upstream removing/reverting the exact line(s) you added, there is **no real conflict** — drop that skill silently, don't surface it, don't ask about it. Only skills where upstream changed something *else* are worth discussing.
3. For the skills that genuinely conflict: tell the user in plain English what upstream changed AND what your local edit was — distinguish the two — then **ask** whether to resolve: pull upstream in, keep local as-is, or hand-merge. Make a default recommendation from the diff. One question covering all real conflicts, not one per skill.
4. On "resolve": hand-merge — apply the upstream file (`git checkout <DIGEST_POST> -- <skill>/<file>`), then re-graft the local edit so its intent survives, verify both are present, and commit. Never blindly overwrite the local edit away.

If step 2 drops every kept skill (all upstream did was strip your customizations), say nothing about conflicts — there's nothing to discuss.

Keep it tight. The user wants to know what changed in the pipeline, not read a diff.

## Check status first (read-only)

`safe-update.sh` only knows the **edit** axis (your copy vs the lock) and learns it mid-update. `scripts/skills-status.sh` adds the second axis the lockfile alone hides — your copy vs **current upstream** — and mutates nothing, so run it before deciding to update:

```bash
bash scripts/skills-status.sh
```

It classifies each lock-tracked skill by comparing three tree SHAs (`local` = your working copy, `lock` = the version you installed from, `upstream` = the source repo now):

- **clean** — matches upstream, untouched.
- **edited, on latest** — your edits sit on the current upstream; nothing to rebase.
- **OUT OF DATE** — upstream moved past your installed version; `safe-update.sh` will pull it.
- **EDITED+STALE (merge needed)** — your edits sit on an *old* upstream; updating will need the hand-merge `safe-update.sh` prints.
- **ORPHAN** — installed but gone from its recorded `skillPath` upstream. Could be a rename, a move between category folders, or a real removal — the script can't tell. Resolve with [Follow renames & moves](#after-the-pull-follow-renames--moves) after the pull.

## What it does

1. Ensures the skills dir is a git repo; commits a **pre-update snapshot** (`PRE`).
2. Runs `npx skills update -g`.
3. Commits the upstream result (`POST`) — so both your version and upstream's now live in git history.
4. **Auto-detects which skills you've edited** and protects them: for each lock-tracked skill it compares your pre-update tree SHA to the lock's `skillFolderHash`; any that diverged are ones you changed. If upstream also changed such a skill, it **restores your version** and prints `git diff PRE POST -- <skill>` so you can review the upstream delta and merge by hand.
5. Prints a change summary and the one-line undo: `git reset --hard PRE`.

Unedited skills update normally. Nothing is ever lost — `PRE` is always in git.

## After the pull: follow renames & moves

`safe-update.sh` handles the two axes a script can see — *clean-behind* (pulled) and *edited-stale* (your version restored, merge diff printed). It **cannot** follow a skill upstream renamed, moved between category folders, or rewrote under a new name: those surface as **ORPHAN** in `skills-status.sh`. Resolving them is model judgment — do it after the pull.

Optional source scope: invoked as `/skills-safe-update <owner-or-source>` (e.g. `mattpocock`), restrict the ORPHAN sweep and re-adds to skills whose lock `source` matches, leaving other sources untouched.

For each ORPHAN:

1. **Rename, move, or gone?** List the upstream tree and look for the same skill under a new name or path:
   ```bash
   gh api repos/<owner>/<repo>/git/trees/<branch>?recursive=1 --jq '.tree[].path' | grep SKILL.md
   ```
   Compare against the orphan's lock `skillPath` (`~/.agents/.skill-lock.json`):
   - **Same name, new folder** (e.g. `in-progress/x` → `engineering/x`) = **move**. Re-add it — `npx skills add <src> -g -s <name> -y` updates the lock `skillPath` in place. Done, no edit to judge.
   - **New name, same job** (e.g. `to-issues` → `to-tickets`) = **rename**. Install the successor (`-s <new-name>`), then step 2. Remove the old one last.
   - **Nowhere upstream** = genuinely **removed**. Keep it if you still use it (it's yours now — add it to `.protected-skills`); else `npx skills remove <name> -g -y`.

2. **Judge the local edit (renames only).** If the orphan carried a local edit, diff it against the successor before replaying:
   ```bash
   diff <old>/SKILL.md <successor>/SKILL.md
   ```
   A rename is often a **rewrite that already covers your edit's intent** — then the edit is *subsumed*; don't replay it. Only graft it forward if the successor genuinely lacks it. When unsure, show the user the old edit + the successor and ask.

3. **Remove the old skill** once the successor is in and any edit is settled: `npx skills remove <old> -g -y` drops the dir, lock entry, and `~/.claude` symlink together.

Then reconcile symlinks and commit the git buffer:

```bash
bash ~/.agents/skills/skills-sync/skills-sync.sh --fix   # link new bodies, relink moved ones
cd ~/.agents/skills && git add -A && git commit -m "update: follow renames/moves"
```

## Why auto-detect (not a pre-edit prompt)

"Protect a skill when I edit it" is tempting to wire as a hook on Edit/Write, but it's unnecessary: a skill *is* edited exactly when its content diverges from the lock's recorded upstream hash. Detecting that at update time needs no list, no event hook, and can't be forgotten. Edit freely; protection is computed for you.

## Optional manual override

If you want to force-protect a skill the auto-detector can't see (e.g. a hand-made skill with no lockfile entry), create `.protected-skills` at the skills-dir root — one skill name per line, `#` comments allowed. It's unioned with the auto-detected set. Most setups never need it.

## Notes

- This skill is hand-maintained, not installed via `npx skills`, so it has no lockfile entry and the package manager leaves it alone.
- The live lockfile lives outside the skills repo (npx writes it to the skills-dir parent). `safe-update.sh` mirrors it into the repo as a tracked `.skill-lock.json` at each snapshot — PRE the old lock, POST the new — so a run reconstructs fully from the git remote. The live file stays authoritative; the in-repo copy is backup only.
- After a clean review, you're already committed — the git buffer stays current for next time.
- Lockfile drift (entries for deleted skills, or skills you added by hand) is a separate one-time cleanup, not handled here: drop dead entries and add untracked ones in `~/.agents/.skill-lock.json`. `skills-status.sh` flags the **ORPHAN** case; [Follow renames & moves](#after-the-pull-follow-renames--moves) resolves it (rename/move/removal) instead of leaving it for hand-cleanup.
- Distinct from `skills-sync` — that skill only reconciles `~/.agents/skills` bodies ↔ `~/.claude/skills` symlinks. It knows nothing about upstream; it's the final symlink-repair step here, not the updater.
- `skills-status.sh` needs `gh` (authenticated) + network to read upstream; offline it reports `upstream UNKNOWN` and only the edit axis is trustworthy.
