# Gas Town, rescored

Extends [#488](https://github.com/caneff/agent-skills/issues/488) under the frame of
[#477](https://github.com/caneff/agent-skills/issues/477). #488 rejected Gas Town on two grounds the
dev has since withdrawn — the Bors-style merge queue forbidding direct pushes to `main`, and Beads
plus Dolt as the tracker of record ("i dont care about dolt"). Both rejections fall, so Gas Town
gets the scoring it never got. It is the only candidate across three surveys
(#485, #486, #488) that cleared the multi-repo bar from source.

Everything below was read first-hand from cloned source at pinned commits. Two facts were
established by live experiment on this machine rather than by reading, and are labelled as such.

| Repo | Commit read | Clone |
|---|---|---|
| Gas Town | `649b832b7672bc7a2dbef26f5983aba6198b819b` (tip of `main`, 2026-07-23) | <https://github.com/gastownhall/gastown> |
| Beads | `40b3232456dfcbe621ea66ee55d635ac56634a1e` (2026-09-01) | <https://github.com/steveyegge/beads> |

Facts already settled in #488 and not redone here: a Rig is a git repo with its own `git_url`
(`internal/config/types.go:614`); the dashboard fetcher iterates every rig in three places
(`internal/web/fetcher.go:655`, `:831`, `:1193`); the sweep short-circuits on
`if info.HasActiveSession` (`internal/polecat/manager.go:3117`); `runPolecatRemove` refuses a healthy
session without `--force` (`internal/cmd/polecat.go:678`); cross-*town* federation is unbuilt but
4-5 repos are 4-5 rigs in one town.

---

## 1. Linux and WSL2 — and the real install footprint

**It runs on Linux, and WSL2 is the documented Windows answer, not a workaround.** Four places say
so in the project's own words:

> "For full tmux-backed workflows on Windows, use WSL or another Linux environment. Native Windows
> shells are best treated as minimal CLI-only environments."
> ([README.md:191](https://github.com/gastownhall/gastown/blob/649b832b/README.md))

`docs/INSTALLING.md:101` and `:151` repeat it, and `docs/phase4-minimum-fix-acceptance.md:13`
describes a "Minimal WSL smoke" test the project runs. There is no WSL-specific install path and
none is needed: inside WSL2 it is the Linux path. **Nothing WSL-specific is documented beyond
"use it"** — no page discusses `/mnt/c` paths, systemd, or clock skew.

### What it actually requires

From `docs/INSTALLING.md:7-32` and `README.md:125-137`, the required host tools for a native install:

| Tool | Version | On this machine |
|---|---|---|
| Go | 1.26.2+ | **absent** |
| Git | 2.20+ | present |
| sqlite3 | any | **absent** |
| ICU4C dev headers (`libicu-dev`) + `pkg-config` | varies | **absent** (`pkg-config: command not found`) |
| Dolt | >= 2.0.7 | **absent** |
| Beads (`bd`) | >= 0.57.0 | **absent** |
| tmux | 3.0+ | present (3.4) |
| Claude Code | >= 2.0.20 | present (2.1.252) |

Checked with `command -v go dolt tmux sqlite3 bd gt` on this WSL2 host (kernel
`6.18.33.2-microsoft-standard-WSL2`): only `tmux` is installed.

**The ICU dependency is a live trap, not a footnote.** Open issue
[#4783](https://github.com/gastownhall/gastown/issues/4783) documents it because it "currently
blocks every build on a clean checkout":

> ```
> # github.com/dolthub/go-icu-regex/internal/icu
> file.cpp:3:10: fatal error: 'unicode/regex.h' file not found
> ```
> "Dolt pulls in `go-icu-regex`, which is cgo. Until cgo can find the ICU headers, **no package in
> the repo builds** — not just the ones that touch Dolt."

That issue is open, meaning the fix is documentation, not a build change. On Debian/Ubuntu WSL2 the
prerequisite line is `sudo apt install -y git sqlite3 libicu-dev pkgconf-pkg-config`
(`docs/INSTALLING.md:61`), plus a Go toolchain and a Dolt binary installed by hand from
dolthub/dolt's own instructions — there is no Linux package for Gas Town. Homebrew installs `gt`,
`bd` and `dolt` together, but only on macOS.

### What runs, once installed

`gt up` boots six kinds of long-lived service (`internal/cmd/up.go:124-137`):

> ```
>   • Dolt       - Shared SQL database server for beads
>   • Daemon     - Go background process that pokes agents
>   • Deacon     - Health orchestrator (monitors Mayor/Witnesses)
>   • Mayor      - Global work coordinator
>   • Witnesses  - Per-rig polecat managers
>   • Refineries - Per-rig merge queue processors
> ```

Dolt and the daemon are ordinary processes. **The Mayor, Deacon, Witnesses and Refineries are each a
Claude Code session in a tmux pane** — the Refinery's own startup builds a `claude` command line and
an initial prompt, "Run `gt prime --hook` and begin patrol"
(`internal/refinery/manager.go:226-260`); the Witness does the same
(`internal/witness/manager.go:159`). For the dev's 4-5 repos that is **1 Mayor + 1 Deacon +
(4-5 Witnesses) + (4-5 Refineries) = 10 to 12 always-on LLM sessions before a single polecat starts
work**, plus a Dolt server and a Go daemon.

**Docker Compose is the easy install and the wrong one here.** `docker-compose.yml` supplies Go,
Dolt, `bd` and tmux inside the image, but its volumes are `agent-home:/home/agent` (a *named
volume*, not a bind mount), `${FOLDER}:/gt` and `dolt-data`. The host's `~/.claude` and
`~/.agents/skills` are not mounted, so under the Docker path the dev's skills, plugins, hooks and
global `CLAUDE.md` do not reach any agent unless he adds bind mounts himself. That is not
documented as a consideration anywhere in `docs/docker.md` or the README.

One more footprint item: rig names "accept letters, digits, and underscores. Hyphens, dots, spaces,
and path separators are not allowed" (`README.md:227`). Every one of the dev's repos is hyphenated,
so `agent-skills` becomes rig `agent_skills`.

---

## 2. Does the dev's Claude Code survive intact? **Yes — his skills, plugins, hooks and `CLAUDE.md` all reach a polecat.**

This was the question that mattered most, and the answer is the good one. Three separate mechanisms
had to be checked, and all three come out clean.

### a. Gas Town adds settings, it does not replace them

A polecat is launched as a `claude` command line built by
`BuildStartupCommandWithAgentOverride` (`internal/config/loader.go:2442`), whose shape is:

```
exec env GT_ROLE=polecat GT_RIG=… GT_POLECAT=… … claude --dangerously-skip-permissions \
    --settings <rig>/polecats/.claude/settings.json '<startup beacon prompt>'
```

The base args come from the `claude` preset — `Command: "claude", Args: []string{"--dangerously-skip-permissions"}`
(`internal/config/agents.go:231-236`) — and `withRoleSettingsFlag` appends the `--settings` pair
(`internal/config/loader.go:1505-1539`).

`--settings` in Claude Code 2.1.252 is documented as *"Path to a settings JSON file or a JSON string
to load **additional** settings from"* (`claude --help`). It is a layer, not a replacement. The flag
that *would* suppress user settings, `--setting-sources`, is **never used**: grepping the whole of
`internal/` and `docs/` for `--setting-sources`, `--system-prompt`, `--append-system-prompt`,
`--plugin-dir` and `--add-dir` returns nothing outside tests. `CLAUDE_CONFIG_DIR` appears only in
the optional per-worker account-rotation feature (`internal/quota/rotate_test.go`), which the dev
would not configure.

**Verified live, not inferred.** Two experiments on this machine with Claude Code 2.1.252:

- *Plugins survive.* Ran `claude --settings <file>` where the file set
  `"enabledPlugins": {"nonexistent@nope": false}` — structurally identical to Gas Town's
  `"enabledPlugins": {"beads@beads-marketplace": false}` — then asked whether the skill
  `ponytail:ponytail` (from the user-level `ponytail@ponytail` plugin) was available. Answer with
  and without `--settings`: **Yes**. The `enabledPlugins` maps merge; the user's plugin is not
  disabled.
- *User hooks survive and still fire.* Ran `claude --settings <file with its own `hooks` block>`
  from inside `/tmp/gastown` and asked it to Write a file there. It came back:

  > "The Write was blocked: `PreToolUse:Write hook error:
  > [/home/caneff/.claude/hooks/require-worktree.sh]: BLOCKED: '/tmp/gastown/HOOKPROBE.txt' is in a
  > repo's PRIMARY checkout…`"

  The user's `~/.claude/settings.json` hooks ran alongside the `--settings` hooks. They are additive.

Skills need no test: user skills live in `~/.claude/skills` (symlinked from `~/.agents/skills`) and
are resolved from the user config directory, which nothing in the launch path redirects. **Wayfinder,
grilling, to-spec and to-tickets are untouched.**

### b. The repo's `CLAUDE.md` is deliberately preserved

`CreatePolecatCLAUDEmd` (`internal/templates/templates.go:237-271`) checks before writing:

```go
// If CLAUDE.md exists (tracked repo file), write to CLAUDE.local.md instead
// to avoid polluting the tracked file with polecat context.
if _, err := os.Stat(claudePath); err == nil {
    …
    return true, os.WriteFile(claudeLocalPath, []byte(content), 0644)
}
```

So the rig's own `CLAUDE.md` is untouched and Gas Town's 296-line polecat doctrine
(`templates/polecat-CLAUDE.md`) goes to `CLAUDE.local.md` beside it. The dev's global
`~/.claude/CLAUDE.md` loads as user memory as it always does.

### c. What Gas Town *does* impose, and where it collides

Nothing is removed, but four things are added to every polecat:

1. **`permissions.defaultMode: "bypassPermissions"`** plus `--dangerously-skip-permissions`
   (`internal/hooks/templates/claude/settings-autonomous.json`). Every approval prompt is gone. That
   is what he wants for polecats, but it is not selective.
2. **A `SessionStart` and `PreCompact` hook running `gt prime --hook`**, and a `UserPromptSubmit`
   hook running `gt mail check --inject` on every single turn (same file). Context is injected
   continuously; its volume cannot be measured without a live town — **not documented**, and not
   measurable from source.
3. **A `PreToolUse` guard that blocks `gh pr create`, `git checkout -b` and `git switch -c`** for any
   Gas Town agent. Its own help text is unambiguous
   (`internal/cmd/tap_guard.go:39-60`):

   > "Gas Town workers push directly to main. PRs add friction that breaks the autonomous execution
   > model (GUPP principle). This guard blocks: `gh pr create`, `git checkout -b` (feature
   > branches), `git switch -c`"

   This is a direct collision with the dev's Gate 1 (other people's repos get a pushed branch and a
   hand-drafted PR command, never a direct land). **It is removable, and documented as removable**:
   `mergeEntries` treats an override entry with an empty hooks list as an explicit disable
   (`internal/hooks/merge.go:89-118`), and `gt hooks override polecat` is the documented way to write
   one (`docs/HOOKS.md:93-100`). Cost: one override file per role, and knowing to write it.
4. **Guards against `sudo` and every package-manager install** in the autonomous template. Harmless.

The reverse direction matters too: **his** hooks fire inside polecats.
`require-worktree.sh` passes, because a polecat's directory is a linked worktree of the rig's bare
`.repo.git` (`WorktreeAddFromRef`, `internal/polecat/manager.go:1009`) so `git_dir != common_dir`.
`block-dangerous-git.sh` blocks only `gh pr merge`, `reset --hard`, `git clean -f`, `branch -D` and
`checkout .` — none of which a polecat runs on the `gt done` path. `sync-primary-main.sh`
(PostToolUse, fetches and fast-forwards `main` in a primary checkout) would run inside every polecat
turn; it is already flagged as a rogue fourth actor on #480 and should die under any host.

**Bottom line on question 2: his Claude Code survives. This is the line Gas Town was most likely to
fail, and it passes.**

---

## 3. Workspace at launch or mid-run? **At launch. Strictly before the agent.**

`gt sling` spawns the polecat, and the spawn path creates the worktree at
`internal/polecat/manager.go:1009`:

```go
// git worktree add -b polecat/<name>-<timestamp> <path> <startpoint>
if err := repoGit.WorktreeAddFromRef(clonePath, branchName, startPoint); err != nil {
```

Everything that follows in `Spawn` — the `CLAUDE.local.md`, the shared-beads redirect, `PRIME.md`,
the overlay files, the `--settings` install, the setup hooks — happens in that directory while no
agent exists. Only afterwards does `sling.go:1100` call `StartSession()`, with a rollback if the
session fails:

```go
freshlySpawned := newPolecatInfo != nil
if freshlySpawned {
    pane, err := newPolecatInfo.StartSession()
    if err != nil {
        rollbackSpawnedPolecat("Session failed")
```

This is the one line where Gas Town beats Claude Code outright. Claude Code's background sessions —
the `claude agents` rows, which is the surface in use — have no eager-worktree option
(#478, #484), and #478's fix is to pre-make worktrees and point rows at them. Gas Town does it by
construction.

---

## 4. Tickets authored elsewhere: can 4-5 repos each sync their own GitHub issues into one town?

**Yes, architecturally — and it is entirely on the Beads side. Gas Town knows nothing about it.**

`grep` for `bd github`, `github sync` and `github pull` across all of `internal/`, `docs/` and
`README.md` returns **zero hits**. Gas Town has no import command, no scheduler entry, no doctor
check for GitHub issues. The bridge is `bd`'s, run by hand.

### The per-rig question, settled

#488 could not determine this because `bd github sync` takes one `github.owner`/`github.repo` pair
and `RigEntry.BeadsConfig` looked like it might carry per-rig GitHub settings. **It does not** —
it carries only two fields (`internal/config/types.go:630`):

```go
type BeadsConfig struct {
	Repo   string `json:"repo"`   // "local" | path | git-url
	Prefix string `json:"prefix"` // issue prefix
}
```

The per-rig scoping comes from somewhere else, and it works: **each rig gets its own Beads database
on the one shared Dolt server.** `gt rig add` runs `bd init --prefix <p> --database <rigname>
--server --server-port <town port>` (`internal/rig/manager.go:614-628`), and polecats reach it
through a redirect file rather than their own copy (`setupSharedBeads`,
`internal/polecat/manager.go:1029`). On the Beads side, `github.owner` and `github.repo` are
**project-level keys stored in the Dolt database**, not in `config.yaml` — the YAML-only namespace
list in `docs/reference/configuration.md:78-90` includes `github.token` (a secret) but not
`github.owner`/`github.repo`. Database-stored means per-database means **per rig**.

So the working setup is: in each rig, `bd config set github.owner caneff`, `bd config set
github.repo <repo>`, `GITHUB_TOKEN` in the environment, then `bd github sync --pull-only` per rig.
**No worked multi-repo example exists** — checked `docs/cli-reference/github.md`,
`docs/reference/configuration.md`, `docs/CLI_REFERENCE.md` and all of Gas Town's docs. The
conclusion above is assembled from the config-scoping rules and the per-rig `--database` call, not
copied from a documented recipe.

### Is the bridge one-way? **No — and that is the hazard.**

`bd github sync` is bidirectional by default (`docs/cli-reference/github.md`):

> "By default, performs bidirectional sync: Pulls new/updated issues from GitHub to beads; Pushes
> local beads issues to GitHub. Use `--pull-only` or `--push-only` to limit direction."

Conflicts default to `--prefer-newer` (also `--prefer-github`, `--prefer-local`). **A ticket edited
in Beads is pushed back to the GitHub issue on the next unrestricted sync.** Worse, a bead that has
no external ref is *created* as a brand-new GitHub issue — `Tracker.CreateIssue`
(`/tmp/beads/internal/github/tracker.go:136`) calls `t.client.CreateIssue(ctx, issue.Title,
issue.Description, labels)`. A Gas Town rig's database is full of internal machinery beads — MR
beads, agent beads, wisps, molecules — so **an unscoped `bd github sync` in a rig would file that
machinery as GitHub issues on the dev's repo.** The safe forms are `--pull-only` always, or
`--push-only --issues <ids>` / `--parent <id>` when a push is genuinely wanted.

---

## 5. The daily loop, walked through concretely

His loop: grilling and wayfinder produce a batch of ready tickets on GitHub issues; he burns them
down one at a time across 4-5 repos. Here it is on Gas Town, with the hand-work named.

1. **Plan.** Unchanged — Claude Code, wayfinder, `/to-spec`, `/to-tickets`, GitHub issues. Confirmed
   possible by question 2: the skills load.
2. **Import.** *By hand, per rig.* `cd ~/gt/<rig> && bd github sync --pull-only`. Nothing in Gas Town
   runs this; nothing schedules it. Four or five commands, or a shell loop he writes.
3. **Assign.** `gt sling <bead-id> <rig>` — "Assign work to an agent (THE unified work dispatch
   command)" (`internal/cmd/sling.go:29`). Either he types it, or he attaches to the Mayor
   (`gt mayor attach`) and tells an LLM coordinator to sling for him. **He should type it** — #487
   already rejected the coordinating-LLM shape on prior art, and Gas Town's Mayor is exactly that
   shape. Typing `gt sling` per ticket is the same gesture as launching an agent today.
4. **Work.** The polecat gets its worktree at launch, its branch `polecat/<name>-<ts>`, his skills
   and hooks, and Gas Town's doctrine. It works one bead — the template's "SINGLE-TASK FOCUS"
   section forbids it from wandering (`templates/polecat-CLAUDE.md:29-38`).
5. **Finish.** The polecat runs `gt done` — "Submits the current branch to the merge queue …
   Notifies the Witness with the exit outcome … Exits the polecat session"
   (`internal/cmd/done.go:34-42`). The polecat is not allowed to sit idle; the template calls that
   "THE IDLE POLECAT HERESY".
6. **Merge.** The Refinery batches pending MRs, runs verification gates on the merged stack, merges
   the batch to `main`, and bisects to isolate a failure (`README.md:651-661`). **No human gate, no
   PR, no review step exists anywhere in the product** — `grep -i review` across `docs/glossary.md`
   finds only formulas. This is closer to his stated model than to a PR flow: "My insight is after
   the fact: small honest commits, `/landed` or `git log -p`, revert if wrong."
7. **See it.** `gt dashboard` (web, port 8080, all rigs), `gt agents` (CLI), or `gt feed` (TUI).
   Requirement 4 is met, as #488 already proved from the fetcher.

### The friction, named

- **Import is manual and per-rig, forever.** Four or five `bd github sync --pull-only` calls before
  every burn-down, and a bead edited on the Gas Town side silently diverges from its GitHub issue
  until he syncs back — with the create-new-issues hazard above waiting if he syncs back unscoped.
- **Two copies of every repo.** `gt rig add <name> <url>` clones into `~/gt/<rig>/`. The `--local-repo`
  flag is only "Local repo path to share git objects" (`internal/cmd/rig.go:369`) — an alternates
  optimisation, not adoption of his existing checkout. His `~/src/<repo>` and his editor stay where
  they are, disconnected from where the agents work.
- **A rig is a directory tree, not a checkout.** Each rig holds `.repo.git` (bare), `mayor/rig`,
  `witness/rig`, `refinery/rig`, `crew/*` and `polecats/*` — several worktrees per repo before any
  work starts.
- **Gate 1 needs the fork path.** See below.
- **10-12 always-on LLM sessions** for 4-5 rigs (question 1), each priming and patrolling on a timer.
- **New vocabulary as the operating surface.** Polecats, convoys, molecules, wisps, slinging, GUPP,
  MEOW, the Wasteland. Not decoration — it is what the commands and the docs are named.

### Gate 1 — repos he does not own

`gt rig add --push-url <fork> --upstream-url <upstream>` is supported and documented
(`docs/guides/fork-rig-setup.md`), with the invariant "`origin`'s fetch URL is upstream, `origin`'s
push URL is your fork". But the guide states its own limitation plainly:

> "**Current limitation: the refinery is not yet fork-aware.** Even a correctly-configured fork rig
> will, today, have its refinery attempt to **merge polecat branches into the fork's `main`** rather
> than open a PR to upstream. … the behavioral half — refinery raising PRs to upstream instead of
> merging to `origin` — is tracked in
> [gastownhall/gastown#1794](https://github.com/gastownhall/gastown/issues/1794) and is not yet
> implemented.
>
> Until then, for strict PR-only behavior:
> - Do **not** start the refinery. Park the rig with `gt rig park <rig>`.
> - Use the polecat → feature branch → manual PR path. Push the branch to your fork and open the PR
>   by hand."

So Gate 1 works — parked rig, no refinery, the `pr-workflow` guard overridden off, manual PR. It is
a documented second mode, not the main line, and it means his non-owned repos get a different
workflow from his own ones.

---

## 6. Maintenance, settled from the git history

**`main` is genuinely stale. Development is genuinely happening. Both are true, and the second does
not rescue the first.**

Read from a full clone (140 remote branches). Note: `rtk` truncates long command output at 50 lines
— the first histogram this research produced was wrong for that reason, and every figure below was
re-taken through `rtk proxy`.

**Commits on `main` by month:**

| Month | Commits |
|---|---|
| 2025-12 | 1985 |
| 2026-01 | 1199 |
| 2026-02 | 2245 |
| 2026-03 | 1426 |
| 2026-04 | 234 |
| 2026-05 | 381 |
| 2026-06 | 159 |
| 2026-07 | 141 |
| 2026-08 | **0** |
| 2026-09 | **0** |

Last commit on `main`: `649b832b`, **2026-07-23**, "Merge pull request #4568". Newest release:
**v1.2.1, 2026-06-06**. `pushed_at` from the API is 2026-09-01, and that is what makes it look
alive — but **no remote branch in the clone is newer than 2026-07-23 either**
(`git for-each-ref --sort=-committerdate`), so the recent `pushed_at` is PR-ref and fork activity,
not branch work landing.

**Is development happening on branches?** Not in the clone's branches, but yes in PRs: #4795, #4794,
#4792, #4791 all updated 2026-09-01, #4790 on 2026-08-31. Issues are live too — #4793, #4789, #4788,
#4787 all filed 2026-08-31/09-01. **So the project is being worked; nothing has merged to `main` in
six weeks and nothing has shipped in three months.**

**Contributors.** 505 distinct author names on `main` all-time, but most are agent identities
(`mayor`, `furiosa`, `gastown/crew/max`, `gastown/refinery`). Deduplicating by email since
2026-05-01 gives 48 addresses, dominated by three:

| Email | Commits since 2026-05-01 |
|---|---|
| thalia.geraghty@fiserv.com (and her named agents) | 350 |
| Bella-Giraffety | 160 |
| steve.yegge@gmail.com | 50 |
| emmanuel.sciara@gmail.com | 18 |
| everything else | < 13 each |

All-time, `steveyegge` has 2321 commits to the next human's ~450. A real bus factor, and the author
is now the third-largest recent contributor to his own project.

**Sunset or roadmap signal:** none. Not archived, MIT, 17,886 stars, 450 open issues, no deprecation
notice anywhere in the README or docs.

**The signal that actually matters is a bug report, not a commit count.** Open issue
[#4793](https://github.com/gastownhall/gastown/issues/4793), filed 2026-09-01:

> "gastown 1.2.1 queries a beads column that no longer exists; 8 defects, no fixed release …
> We originally diagnosed this on 1.1.0, upgraded to 1.2.1 specifically to clear it, and re-ran the
> whole set. **The upgrade fixed nothing** … `brew info gastown` shows no newer version, so there is
> currently no release a user can upgrade to. … **Not workable around.** Not by config, not by
> patching a query, not by a compatibility view — the binary contains no post-split code path at
> all. Only a new release fixes it."

Beads split `depends_on_id` into three columns; the shipped `gt` binary references the old name 101
times. Beads itself is committing daily (its tip is 2026-09-01); Gas Town's `main` has not moved
since July. **The released version of Gas Town is currently broken against the current version of
its own mandatory dependency, and there is no release that fixes it.** `go install …@latest` builds
from the same stale `main`.

---

## 7. The deletion-policy weakness — confirmed, and smaller than it looks

**Confirmed.** `grep` for a `git worktree lock` across `internal/git/` and all of `internal/`
returns exactly one hit, and it is not one: `internal/cmd/mq_integration.go:144` "acquiring land
worktree lock" is a `flock` on the merge-queue land operation, not `git worktree lock`. **Gas Town
never sets a git-level lock.** Its whole liveness policy — the `tmux has-session` probe, the
heartbeat file, the PID `Signal(0)` fallback, the per-polecat flock, the uncommitted/stash checks,
the pending-MR refusal, the cwd-inside-worktree refusal — lives inside `gt`.

The one unguarded force path is confirmed at `internal/doctor/crew_check.go:283-296`:

```go
func (c *CrewWorktreeCheck) Fix(ctx *CheckContext) error {
	...
	for _, wt := range c.staleWorktrees {
		// Use git worktree remove to properly clean up
		mayorRigPath := filepath.Join(ctx.TownRoot, wt.rigName, "mayor", "rig")
		removeCmd := exec.Command("git", "worktree", "remove", "--force", wt.path)
```

No liveness check, unconditional `--force`, reached by `gt doctor --fix` — which the README tells
every new user to run during install (`README.md:212`).

**How much does it matter given he runs other tooling in the same repos? Less than #488 implied,
for a structural reason.** Gas Town's polecat worktrees belong to a *different repository object* —
`~/gt/<rig>/.repo.git` — from his own checkouts at `~/src/<repo>`. `land`'s sweep enumerates
`git worktree list` for the repo it is standing in (`flow/bin/land:93-107`) and would never see
them. Claude Code's own sweep manages `.claude/worktrees/` of the repo it launched in. And under
adoption, `land` is deleted anyway. So the realistic exposure is three things:

1. **`gt doctor --fix`**, narrow scope (stray cross-rig *crew* worktrees only) but genuinely
   unguarded, and it is a command he will be told to run.
2. **`gt polecat nuke`**, which kills the tmux session first, unconditionally, then removes with
   `nuclear=true` (`internal/cmd/polecat.go:1864`) — a deliberately destructive command with a name
   that says so, and it still pushes the branch first.
3. **His own hand.** A plain `git worktree remove` typed against a polecat path is not stopped by
   anything. Claude Code's lock does stop that; nothing in Gas Town does.

Set against it: Gas Town's guard covers a case a lock does not — an agent that is alive after its
lock was released, which is precisely the `t294` failure. **Neither policy dominates. Claude Code
is stronger against external tools; Gas Town is stronger against a stale lock.** That is a real
downgrade on the line #485 decided the host on, but a narrower one than "no deletion policy".

---

## Bottom line

**No. Gas Town does not beat staying on Claude Code with the `claude agents` view — but the reason
has changed completely, and it is worth saying which reason.**

With the merge queue and Beads accepted, Gas Town wins on real lines. It makes the workspace at
launch, which is the single defect Claude Code has and the thing #478 exists to work around. It
spans 4-5 repos in one dashboard by construction. It has a liveness-aware deletion policy — the only
one of the eight-plus candidates surveyed that is documented at all. **And, the finding that would
have mattered most: the dev's Claude Code survives intact — skills, plugins, hooks and `CLAUDE.md`,
verified live, not inferred.** Gas Town adds settings; it does not replace them. Wayfinder and the
planning skills were never at risk.

What kills it now is not design; it is **the state of the project and the size of the move.**

*The state.* `main` has not moved since 2026-07-23. Nothing has shipped since 2026-06-06. The
shipped release is broken against the current version of its own mandatory dependency, with a
2026-09-01 issue saying "there is currently no release a user can upgrade to" and "not workable
around". Requirement 2 in #477 is "dead or sunsetting" — Gas Town is neither dead nor sunsetting, it
is *stalled with a broken release*, which for an adopter today is worse than dead: he would be
installing a known-broken binary and betting on a merge that has not happened in six weeks. This
alone is disqualifying and it is the only reason that needs to hold.

*The size.* Even with a healthy release, this is not a viewer he bolts on. It is an operating model
that replaces where his repos live, how work is dispatched, how it lands, and what runs on his
machine.

### What adopting it would cost, concretely

**What he stops doing.** `land`, `pushpr`, `require-worktree.sh`, the worktree allow-list, the
primary-checkout hook, `EnterWorktree` — all die, which is the delete list from #482 achieved in one
move. His `.claude/worktrees/` model goes with them. Reviewing before a merge stops entirely: the
Refinery merges the batch, and he reads `git log` afterwards. He stops working in `~/src/<repo>` if
he wants his editor near the agents.

**What he starts doing.** Installing Go, Dolt, sqlite3, `libicu-dev` and `pkg-config` on WSL2, and
building past a cgo failure that has an open issue for exactly that reason. Running `gt up` — a Dolt
server, a Go daemon, and 10-12 always-on Claude Code sessions for 4-5 rigs. Re-cloning every repo
into `~/gt` under an underscored name. Running `bd github sync --pull-only` per rig, by hand, every
time, and being careful never to sync back unscoped or the town's internal beads become GitHub
issues. Writing a `gt hooks override polecat` file to disable the guard that blocks `gh pr create`.
Parking the rig and skipping the Refinery on every repo he does not own, because the fork path is
half-built (#1794). Learning polecats, convoys, molecules, wisps and GUPP as the daily interface.

**What breaks.** The GitHub issue tracker stops being the tracker of record and becomes an upstream
he pulls from; every ticket now has two homes and drifts between syncs. Gate 1 gets a second,
different workflow. `sync-primary-main.sh` starts firing inside polecats. `gt doctor --fix` — the
command the README tells him to run — can force-remove a worktree with no liveness check. And he
inherits a bus factor whose top contributor is no longer the author.

### What could not be determined

- **The context volume Gas Town injects per turn.** `gt prime --hook` runs at SessionStart and
  PreCompact and `gt mail check --inject` runs on *every* UserPromptSubmit
  (`internal/hooks/templates/claude/settings-autonomous.json`). How many tokens that is cannot be
  read from source and needs a live town. Not documented in `docs/PRIMING.md`'s public form, the
  README, or `docs/reference.md`.
- **A worked multi-repo GitHub-sync recipe.** Question 4's answer is assembled from the per-rig
  `bd init --database` call and Beads' config-scoping rules. No example of 4-5 rigs each bound to
  their own GitHub repo exists in either project's docs — checked `docs/cli-reference/github.md`,
  `docs/reference/configuration.md`, `docs/CLI_REFERENCE.md`, and all of Gas Town's `docs/`.
- **Whether `main` will move again.** PRs and issues are live as of 2026-09-01; nothing has merged
  since 2026-07-23. No maintainer statement explains the gap. Checked the README, `CHANGELOG.md`,
  `RELEASING.md`, and the recent issue and PR lists — no roadmap or hiatus notice.
- **What the flow becomes with `merge_queue.enabled: false`.** Carried forward unresolved from #488.
  The field exists (`internal/refinery/engineer.go:104-105`, default `true` at `:185`); the
  consequence of turning it off is documented nowhere. The fork guide's "park the rig, do not start
  the refinery" is the nearest documented answer, and it is a different mechanism.
