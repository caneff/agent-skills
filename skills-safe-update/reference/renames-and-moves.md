# Follow renames & moves (ORPHAN resolution)

`safe-update.sh` handles the two axes a script can see — *clean-behind*
(pulled) and *edited-stale* (your version restored, merge diff printed). It
**cannot** follow a skill upstream renamed, moved between category folders,
or rewrote under a new name: those surface as **ORPHAN** in
`skills-status.sh`. Resolving them is model judgment — do it after the pull.

Optional source scope: invoked as `/skills-safe-update <owner-or-source>`
(e.g. `mattpocock`), restrict the ORPHAN sweep and re-adds to skills whose
lock `source` matches, leaving other sources untouched.

For each ORPHAN:

1. **Rename, move, or gone?** List the upstream tree and look for the same
   skill under a new name or path:
   ```bash
   gh api repos/<owner>/<repo>/git/trees/<branch>?recursive=1 --jq '.tree[].path' | grep SKILL.md
   ```
   Compare against the orphan's lock `skillPath` (`~/.agents/.skill-lock.json`):
   - **Same name, new folder** (e.g. `in-progress/x` → `engineering/x`) =
     **move**. Re-add it — `npx skills add <src> -g -s <name> -y` updates the
     lock `skillPath` in place. Done, no edit to judge.
   - **New name, same job** (e.g. `to-issues` → `to-tickets`) = **rename**.
     Install the successor (`-s <new-name>`), then step 2. Remove the old one
     last.
   - **Nowhere upstream** = genuinely **removed**. Keep it if you still use
     it (it's yours now — add it to `.protected-skills`); else
     `npx skills remove <name> -g -y`.

2. **Judge the local edit (renames only).** If the orphan carried a local
   edit, diff it against the successor before replaying:
   ```bash
   diff <old>/SKILL.md <successor>/SKILL.md
   ```
   A rename is often a **rewrite that already covers your edit's intent** —
   then the edit is *subsumed*; don't replay it. Only graft it forward if the
   successor genuinely lacks it. When unsure, show the user the old edit +
   the successor and ask.

3. **Remove the old skill** once the successor is in and any edit is
   settled: `npx skills remove <old> -g -y` drops the dir, lock entry, and
   `~/.claude` symlink together.

Then reconcile symlinks and commit the git buffer:

```bash
bash ~/.agents/skills/skills-sync/skills-sync.sh --fix   # link new bodies, relink moved ones
cd ~/.agents/skills && git add -A && git commit -m "update: follow renames/moves"
```
