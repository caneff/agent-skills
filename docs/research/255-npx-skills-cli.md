# `npx skills` v1.5.22 behavior — lock, hash, update/list/install semantics

Ticket: #256 (child of map #255)
Question: characterize how `npx skills` v1.5.22 behaves so the repo's bespoke
skills-update tooling (`skills-safe-update/scripts/safe-update.sh`,
`skills-status.sh`) can be rebuilt on the CLI's lock format and hashing.

Sources are PRIMARY: the published npm package
(`skills@1.5.22`, `https://registry.npmjs.org/skills/-/skills-1.5.22.tgz`,
repo `vercel-labs/skills`), its bundled source `dist/cli.mjs` (line numbers
below are from that file inside the v1.5.22 tarball), the CLI's own `--help`,
and read-only probes of this machine's global lock and live `ls -g --json`.
Every load-bearing claim is cited to a command run or a source line.

---

## Bottom line — the ticket's premise is inverted, read this first

The ticket assumes global `-g` mode has moved to a `skills-lock.json` **v1**
lock storing **`computedHash`** (a reproducible SHA-256 content hash), retiring
the old `.skill-lock.json` **v3** with **`skillFolderHash`**. **That is not what
v1.5.22 does.** There are two *separate, coexisting* locks split by scope, and
the split is the opposite of the assumption:

| | Global (`-g`) lock | Project (cwd) lock |
|---|---|---|
| File | `~/.agents/.skill-lock.json` (or `$XDG_STATE_HOME/skills/.skill-lock.json`) | `<cwd>/skills-lock.json` |
| Version | **3** | **1** |
| Hash field | **`skillFolderHash`** | **`computedHash`** |
| Hash meaning | git **tree object SHA-1** for github sources; SHA-256 content hash only for tarball/local | always the SHA-256 content hash |
| Reproducible offline | **No** for github sources (git-tree SHA); yes for tarball/local | Yes, when on-disk folder == hashed file set |
| Written by | `addSkillToLock` (`dist/cli.mjs:3522`) | `addSkillToLocalLock` (`dist/cli.mjs:972`) |

Confirmed live on this machine (read-only): `~/.agents/.skill-lock.json` exists,
`version: 3`, 47 skills, each entry carries `skillFolderHash` (e.g.
`"c817f6f36acd483294144694a935a76d3e3eb101"` — 40 hex chars = a git tree
SHA-1, not a SHA-256). There is **no** `~/.agents/skills-lock.json`.

```
$ node -e '...require("/home/caneff/.agents/.skill-lock.json")...'
version: 3
num skills: 47
sample entry keys: [ source, sourceType, sourceUrl, skillPath,
                     skillFolderHash, installedAt, updatedAt ]
```

**Implication for the tooling.** The repo manages the *global* `~/.agents/skills`
tree, whose lock is still `.skill-lock.json` v3 with `skillFolderHash`. The
`skills-lock.json` v1 / `computedHash` world is *project-scope only* and is not
what governs the global tree. A rebuild targeting "the new v1 lock" would be
pointed at a file the CLI never writes in global mode. Decide deliberately
whether the tooling stays on the v3 global lock, or whether the repo switches to
managing skills as a *project* checkout (where `computedHash` applies and is
recomputable). This choice is the real fork the design waits on.

---

## 1. Global lock — location, name, and whether the old v3 is still read

Global mode reads and writes `.skill-lock.json`, **version 3**, at
`$XDG_STATE_HOME/skills/.skill-lock.json` if `XDG_STATE_HOME` is set, else
`~/.agents/.skill-lock.json` — i.e. the **parent** of `~/.agents/skills`, not
inside it.

> `dist/cli.mjs:3477` `const LOCK_FILE = ".skill-lock.json";`
> `dist/cli.mjs:3478` `const CURRENT_VERSION = 3;`
> `dist/cli.mjs:3479-3483`
> ```js
> function getSkillLockPath() {
>   const xdgStateHome = process.env.XDG_STATE_HOME;
>   if (xdgStateHome) return join(xdgStateHome, "skills", LOCK_FILE);
>   return join(homedir(), AGENTS_DIR, LOCK_FILE);   // AGENTS_DIR = ".agents"
> }
> ```

It does **not** "still read the old v3" as legacy — v3 *is* the current global
format. `readSkillLock` treats anything **below** v3 as empty (discards it):

> `dist/cli.mjs:3491` `if (parsed.version < CURRENT_VERSION) return createEmptyLockFile();`

So a pre-v3 global lock is silently dropped; a v3 lock is used as-is. Global
mode never reads `skills-lock.json`, and project mode never reads
`.skill-lock.json` — the two functions (`readSkillLock` vs `readLocalLock`) are
wired to different filenames and never cross.

## 2. `computedHash` (and `skillFolderHash`) algorithm — reproducibility

**`computedHash` (project lock)** is the SHA-256 produced by
`computeSkillFolderHash`:

> `dist/cli.mjs:944-958`
> ```js
> async function computeSkillFolderHash(skillDir) {
>   const files = [];
>   await collectFiles(skillDir, skillDir, files);      // recursive, skips .git and node_modules
>   files.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
>   const hash = createHash("sha256");
>   for (const file of files) {
>     hash.update(file.relativePath);                   // POSIX-slashed path, relative to skillDir
>     hash.update(file.content);                        // raw bytes, no separator
>   }
>   return hash.digest("hex");
> }
> ```
> `collectFiles` (`dist/cli.mjs:959-971`) walks every file, skips directories
> named `.git` / `node_modules`, and slashes `\` → `/` in the relative path.

No canonicalization of file *content* (raw bytes), no field separators between
path and content, ordering by `localeCompare` of the POSIX relative path.
**This is reproducible outside the CLI** — verified empirically below.

Caveat: on a blob/registry install the project lock stores `snapshotHash`
instead, computed by `computeSnapshotHash` (`dist/cli.mjs:3767`) — same idea
(sha256, sort by path, `update(path)+update(contents)`) but over the *downloaded
registry file set*, not the on-disk folder:

> `dist/cli.mjs:4905` `const computedHash = blobResult && "snapshotHash" in skill ? skill.snapshotHash : await computeSkillFolderHash(skill.path);`

**`skillFolderHash` (global lock)** is heterogeneous and mostly **not**
reproducible from disk:
- github source → the **git tree object SHA-1** returned by
  `getSkillFolderHashFromTree` from the GitHub tree API
  (`dist/cli.mjs:3648-3656`, and used at `4877`/`4880`). Git computes tree
  SHA-1s over its own tree-object encoding; you cannot reproduce it with a
  plain content hash.
- tarball/local temp source → falls back to `computeSkillFolderHash`
  (`dist/cli.mjs:4882`), which *is* reproducible.

This machine's global entries are all github-sourced, so their
`skillFolderHash` values are git tree SHA-1s (40 hex chars).

### Empirical reproducibility test (read-only, throwaway temp dirs)

Local-source install — on-disk folder equals the hashed set → recompute matches
**exactly**:

```
$ mkdir localskill localskill/references
$ ... write localskill/SKILL.md + references/notes.md ...
$ (in fresh proj2) npx skills@1.5.22 add ../localskill -a claude-code --copy -y
skills-lock.json:
  "my-test-skill": { "source": "../localskill", "sourceType": "local",
                     "computedHash": "84a7ca6ddc0a1214f157c9c802c21a243aa00514ebe9da413786d0871fc50504" }
recompute over .claude/skills/my-test-skill (same algorithm): 84a7ca...0504   ← MATCH
```

Github-source install — on-disk folder does **not** equal the hashed set →
recompute **differs**:

```
$ (in fresh proj) npx skills@1.5.22 add vercel-labs/agent-skills -s vercel-optimize -a claude-code -y
skills-lock.json computedHash: ad0ef9c5...b62cc44
on-disk .claude/skills/vercel-optimize contains ONLY SKILL.md
recompute over that folder:    9d4ace02...eeec33      ← DIFFERS
```

Why: upstream `skills/vercel-optimize/` has `SKILL.md`, `AGENTS.md`,
`README.md`, `metadata.json`, `lib/`, `references/`, `scripts/`
(GitHub contents API), but the install placed only `SKILL.md` on disk, while the
stored `computedHash`/`snapshotHash` covers the full upstream folder. The
installed `SKILL.md` is byte-identical to upstream (`diff` = IDENTICAL), so the
divergence is *file-set*, not content mangling.

**Tooling consequence:** "recompute the on-disk folder hash and compare to the
lock" is a reliable edit-detector **only** when the on-disk folder is the same
file set that was hashed — true for `local`-source full-folder installs, false
for github installs that materialize a partial folder. For the global v3 lock,
the github `skillFolderHash` is a git-tree SHA-1 and is not content-recomputable
at all.

## 3. `update` on a locally-edited skill — warn / prompt / skip / overwrite?

**`update` never inspects the local on-disk copy.** It compares the *upstream*
against the *hash stored at install time*, and if upstream moved it reinstalls
by shelling out to `add … -y`, which overwrites in place. There is **no**
local-edit detection, **no** prompt about local divergence, and **no**
`--dry-run`/preview flag (the only update flags are `-g`, `-p`, `-y` per
`--help`).

Global path (`dist/cli.mjs:6511-6519`):

> ```js
> const latestHash = getSkillFolderHashFromTree(tree, entry.skillPath);
> if (latestHash && latestHash !== entry.skillFolderHash) updates.push({ name: skillName, source, entry });
> ```

i.e. "did **upstream** change since I installed?" — `entry.skillFolderHash` is
the install-time upstream hash, not a hash of your working copy. Applying an
update just re-runs `add`:

> `dist/cli.mjs:6595-6605` `spawnSync(process.execPath, [cliEntry, "add", installUrl, "--skill", update.name, ..., "-g", "-y"], …)`

Consequences for a locally-edited skill:
- **Upstream unchanged since install** → `latestHash === entry.skillFolderHash`
  → skill is reported up to date and is **left untouched** (your edits survive,
  by luck, not by guard).
- **Upstream changed** → `add … -y` reinstalls and **silently overwrites** your
  local edits. No warning, no diff, no confirmation.

The only interactive prompt in the update flow is `checkAndPromptForDeletions`
(`dist/cli.mjs:6503`, `6549`, `6672`) — that is about skills **deleted
upstream**, not about protecting local edits.

Skip conditions (global): an entry with no `skillFolderHash` or no `skillPath`
is pushed to `skipped` and reported, never updated
(`dist/cli.mjs:6469-6478`, reason via `getSkipReason`).

Project path is analogous (`updateProjectSkills`, `dist/cli.mjs:6628+`): it only
updates entries that have a `skillPath`; entries without one (notably every
`sourceType: "local"` entry — local installs store no `skillPath`) are shunted
to `legacy` and printed as "cannot be updated automatically"
(`printLegacyProjectSkills`, `dist/cli.mjs:6763`). Updatable project skills are
likewise refreshed by re-running `add … -y`, overwriting in place with no
local-edit check.

**Crux for the data-loss guard:** the CLI provides *zero* protection against
clobbering local edits on update, and no preview. Any safety must live entirely
in the repo's own tooling — snapshot/compare before invoking the CLI, or gate on
a recomputed content hash where that is meaningful (local-source skills).

## 4. `list --json` fields — any staleness signal?

Only identity + source. **No hash, no `installedAt`/`updatedAt`, no
`outdated`/`stale`/`edited`/`modified` flag.** Per-skill object
(`dist/cli.mjs:5851-5866`):

> ```js
> { name, path, scope, agents /* display names */, source, sourceUrl, sourceType }
> ```

Verified live:

```
$ npx skills@1.5.22 ls -g --json
[ { "name": "add-molab-badge",
    "path": "/home/caneff/.agents/skills/add-molab-badge",
    "scope": "global", "agents": ["Claude Code","Codex","GitHub Copilot","Zed"],
    "source": "marimo-team/skills",
    "sourceUrl": "https://github.com/marimo-team/skills.git",
    "sourceType": "github" }, … ]
```

`list` reads the scope-appropriate lock (`getAllLockedSkills()` for `-g`,
`readLocalLock()` otherwise, `dist/cli.mjs:5849`) but deliberately projects out
the hash fields. **The tooling cannot lean on `ls --json` for staleness; it must
read the lock file itself and compute its own comparison.**

## 5. `experimental_install` semantics

`experimental_install` → `runInstallFromLock` (`dist/cli.mjs:5746`). It is
**project-scope only**: it reads `skills-lock.json` from the **cwd** and
reinstalls every entry from upstream into `.agents/skills/`.

> `dist/cli.mjs:5747` `const lock = await readLocalLock(process.cwd());`
> `dist/cli.mjs:5775` restore log: `Restoring N skill(s) from skills-lock.json into .agents/skills/`
> `dist/cli.mjs:5774-5781` per source: `await runAdd([source], { skill: skills, agent: universalAgentNames, yes: true });`
> node_modules entries are handled via `runSync(..., { yes: true })` instead.

- It **does not** read or touch the global `~/.agents/.skill-lock.json`.
- It re-adds from upstream with `yes: true` → **overwrites local edits**, same
  as `update`; there is no local-edit check and no `computedHash` verification
  before overwriting.
- Its job is "restore the project's skills to what the lock says they should be
  from source," not "verify/repair against the stored hash."

## 6. Migration surface (v3 `.skill-lock.json` → v1 `skills-lock.json`)

**There is no migration path, and none is needed in the CLI's model** — because
v3 and v1 are not successive versions of one lock. They are two different files
for two different scopes, both current in v1.5.22 (global stays v3; project is
v1). Neither reader upgrades or imports the other:

- `readSkillLock` discards anything `< 3` (`dist/cli.mjs:3491`).
- `readLocalLock` discards anything `< 1` (`dist/cli.mjs:911`).

There is **no `adopt`/`import` command** that ingests an existing on-disk skill
(or an old lock) into a lock entry. Lock entries — including `source`,
`sourceType`, `skillPath`, and the hash — are only ever written as a side effect
of `add` (and of `update`/`experimental_sync`/`experimental_install`, which all
call `add`). A skill sitting on disk with no lock entry stays unmanaged until it
is re-`add`ed from its source.

How `add` populates the identity fields:
- `sourceType` = parser's classification of the argument: `github`, `git`,
  `gitlab`, `local`, `well-known`, `node_modules` (see `parsed.type` usage at
  `dist/cli.mjs:4888`, `4911`).
- `skillPath` = the repo-relative path to the skill's `SKILL.md`, taken from the
  `skillFiles` map built during discovery (`skillPathValue = skillFiles[skill.name]`,
  global `dist/cli.mjs:4875-4891`, project `4906-4912`). `local`-source installs
  record **no** `skillPath` (observed empirically — the local lock entry had only
  `source`/`sourceType`/`computedHash`), which is why local skills are
  non-auto-updatable (§3).
- `source` = normalized shorthand (`owner/repo`) or, for non-github git,
  the git URL via `getLockSource`/`getProjectLockSourceUrl`
  (`dist/cli.mjs:3855-3864`).

**Tooling consequence:** to bring the existing 47 global skills onto any
different lock/hash scheme, there is no supported in-place converter — entries
must be re-derived (re-`add`ed from source, or the tooling writes the lock
itself). If the tooling keeps using the v3 global lock as-is, the github
`skillFolderHash` values remain git-tree SHA-1s that it cannot independently
recompute for edit detection.

---

## Answers in one line each

1. **Global lock:** `~/.agents/.skill-lock.json` (parent of the skills dir;
   `$XDG_STATE_HOME/skills/.skill-lock.json` if set), **version 3**,
   `skillFolderHash`. Not retired — it *is* the current global format. Global
   mode never reads/writes `skills-lock.json`.
2. **`computedHash`:** SHA-256 over the skill folder — recurse (skip
   `.git`/`node_modules`), sort files by POSIX relative path, `update(path)` then
   `update(rawBytes)` with no separator. **Reproducible** when the on-disk folder
   equals the hashed file set (verified exact for local installs; diverges for
   github installs that materialize a partial folder). It lives in the **project**
   lock only; the global lock's `skillFolderHash` is a git-tree SHA-1 for github
   sources and is **not** content-recomputable.
3. **`update` on a locally-edited skill:** no local-edit detection at all, no
   prompt, no `--dry-run`. Compares upstream to the install-time hash; if upstream
   changed it re-runs `add … -y` and **silently overwrites** local edits;
   if upstream is unchanged the skill is skipped and edits happen to survive.
4. **`list --json`:** `name, path, scope, agents, source, sourceUrl, sourceType`
   only. **No hash and no staleness/edited signal.**
5. **`experimental_install`:** project-scope only; reads `skills-lock.json` from
   cwd, reinstalls every entry from upstream (`add … -y`) into `.agents/skills/`;
   **overwrites** local edits; does not touch the global `.skill-lock.json`.
6. **Migration:** none — v3 (global) and v1 (project) are separate coexisting
   locks, not an upgrade chain; no `adopt`/import command. `source`/`sourceType`/
   `skillPath`/hash are only written by `add` (and the commands that call it);
   `local` installs record no `skillPath`.

## Nothing left undetermined

All six bullets are answered from the CLI source plus read-only live probes. The
only judgement flagged (not a gap) is that the ticket's framing — global mode on
`skills-lock.json` v1 / `computedHash` — does not match v1.5.22; global mode
remains on `.skill-lock.json` v3 / `skillFolderHash`. The design should resolve
which lock the rebuilt tooling targets before implementation.
