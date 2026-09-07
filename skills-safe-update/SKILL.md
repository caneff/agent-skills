---
name: skills-safe-update
description: Update agent skills installed via the `npx skills` package manager without losing local edits — including following upstream renames, folder moves, and rewrites that a plain update would drop as orphans.
disable-model-invocation: true
---

# Safe skills update

`npx skills update` overwrites locally-edited skills — its lockfile records only the *upstream* version (`skillFolderHash`), never your changes. This skill wraps it so edits survive.

## Quick start

```bash
bash scripts/skills-status.sh   # read-only: what's edited vs out of date
bash scripts/safe-update.sh     # do the update, merging your edits with upstream
```

Both run against `~/.agents/skills` (override with `SKILLS_DIR=...`).

`safe-update.sh` exits **non-zero when a merge conflicted**. That is not a
crash: the update ran, and `PRE` and the upstream `POST` are both committed.
What is *not* committed is the merge itself — a conflicted run leaves the
markers in the working tree deliberately, so the hand merge happens on the real
files and the commit that follows records the resolution instead of the
markers. Read the report, do the digest, resolve every marker, then commit.

## Check status first (read-only)

`safe-update.sh` only knows the **edit** axis (your copy vs the lock) and learns it mid-update. `scripts/skills-status.sh` adds the second axis the lockfile alone hides — your copy vs **current upstream** — and mutates nothing, so run it before deciding to update:

```bash
bash scripts/skills-status.sh
```

It classifies each lock-tracked skill by comparing three tree SHAs (`local` = your working copy, `lock` = the version you installed from, `upstream` = the source repo now):

- **clean** — matches upstream, untouched.
- **edited, on latest** — your edits sit on the current upstream; nothing to rebase.
- **OUT OF DATE** — upstream moved past your installed version; `safe-update.sh` will pull it.
- **EDITED+STALE (merge needed)** — your edits sit on an *old* upstream; `safe-update.sh` will three-way merge them, and asks for you only where the hunks overlap.
- **ORPHAN** — installed but gone from its recorded `skillPath` upstream. Could be a rename, a move between category folders, or a real removal — the script can't tell. Resolve with [reference/renames-and-moves.md](reference/renames-and-moves.md) after the pull.

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
DIGEST_MERGED=<space-separated skills merged clean with upstream>
DIGEST_CONFLICTED=<space-separated skills with conflict markers to resolve>
DIGEST_KEPT=<space-separated skills kept whole-file, not merged>
```

A conflicted run stops before the merge commit, so `git status` in
`DIGEST_SKILLS_DIR` is dirty by design until the conflicts are resolved.

```
```

Then:

1. For each changed skill, read its content diff — prose files only, skip pure boilerplate:
   ```bash
   git -C <DIGEST_SKILLS_DIR> --no-pager diff <DIGEST_PRE> <DIGEST_POST> -- <skill>/SKILL.md <skill>/*.md
   ```
2. Write the digest as a short list: **one line per skill that meaningfully changed, in plain English — what changed and why it matters**, not a file stat. Collapse repeated mechanical changes (e.g. "every skill gained an `agents/openai.yaml` OpenAI variant") into a single cross-cutting line.

## Resolve merge conflicts (required, interactive)

`safe-update.sh` three-way merges every skill you edited (see **What it does**
below), so most edited skills need nothing from you. Two anchors do:

- **`DIGEST_CONFLICTED`** — your edit and upstream's overlap. The script exits
  **non-zero** and its per-file report names each file. A text overlap carries
  `<<<<<<< yours` / `>>>>>>> new upstream` markers in the file. The three cases
  with no lines to mark up — you deleted a file upstream changed, upstream
  deleted a file you edited, and a symlink — carry no markers, and the report
  line says which side is sitting in the tree instead. **Nothing in the run is
  committed while any of this stands** — not even the skills that merged
  cleanly. Read both kinds, resolve every marker in the working tree, then
  `git add -A && git commit`.
- **`DIGEST_KEPT`** — skills kept whole-file with no merge attempted. Three
  things land here: you listed the skill in `.protected-skills`; there was no
  merge base for it; or the merge itself failed to write (the script prints
  `merge failed for <skill>` on stderr, and that one is a bug worth reporting,
  not a normal outcome). In every case your files are restored, but brand-new
  files upstream added still land. Read `git -C
  <DIGEST_SKILLS_DIR> --no-pager diff <DIGEST_PRE> <DIGEST_POST> -- <skill>`,
  decide whether upstream changed anything beyond the inverse of your own edit
  — if the whole delta is upstream stripping your customization, drop it
  silently — and hand-merge the rest.

For both: tell the user in plain English what upstream changed AND what their
local edit was — distinguish the two — then ask how to resolve, one question
covering every real conflict, not one per skill. Make a default recommendation
from the diff. Never blindly overwrite the local edit away.

If both anchors are empty, say nothing about conflicts — there is nothing to
discuss.

Keep it tight. The user wants to know what changed in the pipeline, not read a
diff.

## What it does

1. Ensures the skills dir is a git repo; commits a **pre-update snapshot** (`PRE`).
2. Runs `npx skills update -g`.
3. Commits the upstream result (`POST`) — so both your version and upstream's now live in git history.
4. **Auto-detects which skills you've edited**: for each lock-tracked skill it
   compares your pre-update tree SHA to the lock's `skillFolderHash`; any that
   diverged are ones you changed.
5. **Three-way merges** each of those against upstream — the lock's pre-update
   `skillFolderHash` *is* the git tree SHA of the version you installed, so it
   is the merge base. Per file: your edit alone applies, upstream's alone
   applies, both apply when the hunks don't overlap, and overlapping hunks are
   written out with conflict markers. It prints a per-file report (`MERGED` /
   `CONFLICT` / `LOCAL` / `UPSTREAM`) per skill. It commits the merge **only if
   nothing conflicted**; otherwise it exits non-zero and leaves the markers
   uncommitted in the working tree for you to resolve. A skill in `.protected-skills`, or one with
   no reachable base, is kept whole-file and lands in `DIGEST_KEPT` instead.
6. Prints a change summary and the one-line undo: `git reset --hard PRE`.

Unedited skills update normally. Nothing is ever lost — `PRE` is always in git.

## After the pull: follow renames & moves

`safe-update.sh` cannot follow a skill upstream renamed, moved between
category folders, or rewrote under a new name — those surface as **ORPHAN**
in `skills-status.sh`. See
[reference/renames-and-moves.md](reference/renames-and-moves.md) for the
resolution steps and the `/skills-safe-update <owner-or-source>` scoping
form.

## Optional manual override

If you want to force-protect a skill, create `.protected-skills` at the skills-dir root — one skill name per line, `#` comments allowed. It's unioned with the auto-detected set. Most setups never need it.

A listed name is never merged, even when its lockfile hash would give a usable base: naming it here says *keep mine*. It is kept whole-file and reported under `DIGEST_KEPT`.

## Notes

- This skill is hand-maintained, not installed via `npx skills`, so it has no lockfile entry and the package manager leaves it alone.
- The live lockfile lives outside the skills repo (npx writes it to the skills-dir parent). `safe-update.sh` mirrors it into the repo as a tracked `.skill-lock.json` at each snapshot — PRE the old lock, POST the new — so a run reconstructs fully from the git remote. The live file stays authoritative; the in-repo copy is backup only.
- After a clean review, you're already committed — the git buffer stays current for next time.
- Lockfile drift (entries for deleted skills, or skills you added by hand) is a separate one-time cleanup, not handled here: drop dead entries and add untracked ones in `~/.agents/.skill-lock.json`. `skills-status.sh` flags the **ORPHAN** case; [reference/renames-and-moves.md](reference/renames-and-moves.md) resolves it (rename/move/removal) instead of leaving it for hand-cleanup.
- Distinct from `skills-sync` — that skill only reconciles `~/.agents/skills` bodies ↔ `~/.claude/skills` symlinks. It knows nothing about upstream; it's the final symlink-repair step here, not the updater.
- `skills-status.sh` needs `gh` (authenticated) + network to read upstream; offline it reports `upstream UNKNOWN` and only the edit axis is trustworthy.
