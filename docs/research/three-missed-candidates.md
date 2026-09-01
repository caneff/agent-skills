# The three the sweep missed: Gas Town, dmux, OpenKanban

Resolves [#488](https://github.com/caneff/agent-skills/issues/488). Extends
[#485](https://github.com/caneff/agent-skills/issues/485) (shortlist) and
[#486](https://github.com/caneff/agent-skills/issues/486) (breadth sweep, plus its correction comment).

Everything below was read first-hand from each project's own repository. Each project was cloned and
read at a pinned commit:

| Project | Commit read | Clone |
|---|---|---|
| Gas Town | `649b832b7672bc7a2dbef26f5983aba6198b819b` | <https://github.com/gastownhall/gastown> |
| dmux | `8cb3d926631a9349ab67f7ece41d218427ac7e24` | <https://github.com/standardagents/dmux> |
| OpenKanban | `02201ed231e37519541e9d92cd1e66316a7e97cb` | <https://github.com/TechDufus/openkanban> |

No roundups, no third-party reviews. Where a fact is absent from primary sources it is written
"not documented" with the list of what was checked.

---

## The bar

Claude Code wins today because it loses exactly one line — the workspace is taken on first write
rather than at launch — and it is the only candidate with a documented, liveness-aware deletion
policy: it holds a `git worktree lock` for the whole run, and both its sweep and `git worktree
remove` honour that lock. #486 proved from repomon's source that repomon will remove a clean
worktree with a live agent attached (`LaneService::delete` → `worktree::remove(..., false)`, no lock
ever set, no attachment check). **Winning the workspace-at-launch line while losing the deletion
line is not an improvement.**

---

## Gas Town

<https://github.com/gastownhall/gastown> — MIT, Go, 17,887 stars.

### Requirement 1 — does the dashboard span repositories? **Yes. Settled from source.**

The #488 ticket flagged the multi-repo claim as inferred. It is not inferred any more; it is
provable from the data model and the dashboard's own fetcher, without relying on the tagline.

**A "Rig" is a git repository.** The glossary is unambiguous: *"Rig — A project-specific Git
repository under Gas Town management"* and *"Town — The management headquarters (e.g. `~/gt/`). The
Town coordinates all workers across multiple Rigs"*
([docs/glossary.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/docs/glossary.md)).
The registry entry confirms it — each rig carries its own remote:

```go
// internal/config/types.go:614
type RigsConfig struct {
	Version int                 `json:"version"`
	Rigs    map[string]RigEntry `json:"rigs"`
}

type RigEntry struct {
	GitURL      string       `json:"git_url"`
	PushURL     string       `json:"push_url,omitempty"`
	UpstreamURL string       `json:"upstream_url,omitempty"`
	LocalRepo   string       `json:"local_repo,omitempty"`
	...
}
```

([internal/config/types.go](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/config/types.go#L614))

**The dashboard iterates every registered rig.** The web dashboard's fetcher loads
`mayor/rigs.json` and loops over all of them in three separate places — the merge queue, the agent
list, and the rig list:

```go
// internal/web/fetcher.go:655
// FetchMergeQueue fetches open PRs from registered rigs.
	rigsConfigPath := filepath.Join(f.townRoot, "mayor", "rigs.json")
	rigsConfig, err := config.LoadRigsConfig(rigsConfigPath)
	...
	for rigName, entry := range rigsConfig.Rigs {
		...
		prs, err := f.fetchPRsForRepo(repoPath, rigName)
```

([internal/web/fetcher.go](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/web/fetcher.go#L655))

The agent fetcher (same file, ~line 831) builds a `registeredRigs` set from the same file, skips any
session whose rig is not registered, and stamps each returned row with `Rig: rig`; rows are sorted
by rig, then role, then worker (~line 1513). `FetchRigs` (~line 1193) returns one row per rig with
its agent counts. The dashboard is a town-level, all-rigs view by construction — the per-rig
filtering is what has to be added, not the cross-rig aggregation.

Independent corroboration in the docs: the Mayor *"operates from the town level and has visibility
across all Rigs"*
([docs/glossary.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/docs/glossary.md)).

**Requirement 1: PASS.**

One scope correction worth recording: Gas Town's *federation* feature — coordinating across separate
**towns** — is explicitly unbuilt. `docs/design/federation.md` opens with *"Status: Partially
implemented — Infrastructure (Dolt remotes) exists. Core federation features (URI scheme,
cross-workspace queries, delegation) are not yet implemented"*
([docs/design/federation.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/docs/design/federation.md)).
That is irrelevant here: 4-5 repos are 4-5 rigs in **one** town, which is the supported case.

### Deletion policy — from source

**Gas Town is liveness-aware in two independent places, and it is the only one of the three that
is.** It does not use `git worktree lock`; it uses a per-polecat `flock` plus a tmux session-health
check.

**1. The automated sweep refuses to touch a polecat with a live session.** `gt polecat stale
--cleanup` is the auto-nuke path. It only nukes what `assessStaleness` marks stale, and that
function short-circuits on liveness:

```go
// internal/polecat/manager.go:3117
func assessStaleness(info *StalenessInfo, threshold int) (bool, string) {
	// Never clean up if there's uncommitted work
	if info.HasUncommittedWork {
		return false, "has uncommitted work"
	}

	// If session is active, not stale (tmux is source of truth for liveness)
	if info.HasActiveSession {
		return false, "session active"
	}
	...
```

([internal/polecat/manager.go](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/polecat/manager.go#L3117))

`HasActiveSession` comes from a real probe — `tmux has-session -t gt-<rig>-<polecat>`
(`checkTmuxSession`, same file line 3095). There is a deeper liveness ladder used elsewhere in the
codebase — `isSessionProcessDead` (line 2085) reads a heartbeat file with a 3-minute stale threshold,
falls back to `IsAgentAliveChecked`, then to PID `Signal(0)` probing, and *returns false on any
transient failure* so an unreadable state never reads as dead.

**2. The manual remove refuses too.** `gt polecat remove` checks the session before calling into the
manager:

```go
// internal/cmd/polecat.go:678
		// Check if session is running
		if !polecatForce {
			polecatMgr := polecat.NewSessionManager(t, p.r)
			running, _ := polecatMgr.IsRunning(p.polecatName)
			if running {
				removeErrors = append(removeErrors, fmt.Sprintf("%s/%s: session is running (stop first or use --force)", ...))
				continue
			}
		}
```

([internal/cmd/polecat.go](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/cmd/polecat.go#L678))

This matches the documented behaviour exactly — `docs/CLEANUP.md` says `gt polecat remove` *"Removes
polecat worktree/directory (fails if session running)"*
([docs/CLEANUP.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/docs/CLEANUP.md)).
Docs and source agree.

**3. `RemoveWithOptions` layers four more guards** before it touches the filesystem
([internal/polecat/manager.go:1126](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/polecat/manager.go#L1126)):
a per-polecat `flock` against concurrent removes; a `cleanup_status` / uncommitted-work check
(stashes block even under `--force`); a refusal when an MR is still pending in the merge queue
(*"cannot remove polecat %s: MR %s is still pending in merge queue"*, blocked even in nuclear mode
unless `--force`); a refusal when the user's own shell is `cd`'d inside the worktree; and a
best-effort `git push` of unpushed commits before removal. Only then does it call
`repoGit.WorktreeRemove(clonePath, force)` — and `force` is passed through, not hardcoded.

**Does it force? Does it set a lock? Does it check for an attached agent?**
Forces only when the caller asks; never sets a `git worktree lock`; **yes, it checks for an attached
agent** — twice, on both the automated and the manual path.

**The two honest holes:**

- `gt polecat nuke` kills the tmux session *first, unconditionally*, then removes the worktree with
  `nuclear=true`
  ([internal/cmd/polecat.go:1864](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/cmd/polecat.go#L1864)).
  That is a deliberate destructive command with a name that says so, not a sweep — and it still
  pushes the branch before deleting.
- `gt doctor --fix` runs `git worktree remove --force` with no liveness check at all, on misplaced
  cross-rig *crew* worktrees
  ([internal/doctor/crew_check.go:288](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/doctor/crew_check.go#L288)).
  Narrow scope, opt-in command, but it is the one unguarded force path in the codebase.
- Because no `git worktree lock` is ever set, a human running plain `git worktree remove` outside
  `gt` is not stopped. Claude Code's lock does stop that. This is the single line on which Claude
  Code's policy is stronger.

### The rest

- **Workspace at launch: PASS.** `gt sling` spawns the polecat — which creates the worktree via
  `WorktreeAddFromRef` ([manager.go:805](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/polecat/manager.go#L805)) — and only afterwards calls
  `newPolecatInfo.StartSession()`
  ([internal/cmd/sling.go:1102](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/internal/cmd/sling.go#L1102)),
  with a `rollbackSpawnedPolecat` if the session fails to start. Worktree strictly precedes agent.
- **Batch review: PASS.** No mandatory per-ticket interactive gate. Completed work goes to the
  Refinery merge queue, which batches and merges automatically with configurable verification gates
  (`run_tests`, `lint_command`, `max_concurrent`, …)
  ([docs/reference.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/docs/reference.md#L132)).
- **Tickets authored elsewhere: PASS.** Gas Town tracks work in Beads, and `bd` has a first-party
  GitHub integration: `bd github sync` (bidirectional by default), `bd github pull` (`--pull-only`),
  `bd github push`, `bd github status`, `bd github repos`, configured with `github.owner` /
  `github.repo` / `GITHUB_TOKEN`
  ([beads docs/CLI_REFERENCE.md](https://github.com/gastownhall/beads/blob/main/docs/CLI_REFERENCE.md)).
  Pull a wayfinder issue into beads, then `gt sling <bead> <rig>`. Caveat: the GitHub repo is a
  config value, so a multi-repo setup needs per-rig beads configs — `RigEntry.BeadsConfig` exists
  for exactly that, but a worked multi-repo GitHub-sync example is **not documented**.
- **Direct to `main` with no PR: FAIL, by design.** The README is explicit: *"This is a Bors-style
  merge queue — polecats never push directly to main"*
  ([README.md:661](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/README.md)).
  The queue does merge to `main` without a human PR gate, so nothing forces a PR — but the agent
  cannot land the way `land` does today. `merge_queue.enabled` is a config field defaulting to
  `true`; what the flow becomes when it is `false` is **not documented** (checked `docs/reference.md`
  merge-queue table, `README.md` merge-queue section, `docs/CLEANUP.md`).
- **Runs Claude Code: PASS.** *"Claude Code CLI | latest | Default runtime"*; the Mayor is itself a
  Claude Code instance; presets exist for `claude`, `gemini`, `codex`, `cursor`, `copilot`, `amp`,
  `opencode` and others ([README.md](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/README.md#L454)).
- **Platform: Linux fine.** `.goreleaser.yml` builds linux/amd64, linux/arm64 and darwin; there is a
  Dockerfile, a docker-compose.yml and a flake.nix.
- **Maintenance signal: strong but with one wrinkle.** 17,887 stars, created 2025-12-16, not
  archived, MIT, 450 open issues, no sunset notice. Ten-plus contributors, though `steveyegge` has
  4,831 of the commits to the next contributor's 457 — a real bus factor. The wrinkle: GitHub reports
  `pushed_at` 2026-09-01, but the **last commit on `main` is 2026-07-23** (`Merge pull request #4568`),
  and the newest tag/release is **v1.2.1, 2026-06-06**. The recent pushes are branch activity, not
  releases. Six weeks without a `main` commit and three months without a release, against 100+ live
  branches. Alive, but the headline "pushed 2026-09-01" overstates it.

### Cost of adopting it

Gas Town is not a viewer; it is a whole operating model. A town runs a Dolt SQL server, a daemon, a
Mayor, a Deacon and its Dogs, plus a Witness and a Refinery *per rig* — all as tmux-hosted agent
sessions — and it replaces GitHub issues with Beads as the tracker of record and replaces direct
landing with a merge queue. The vocabulary (polecats, convoys, molecules, wisps, slinging, GUPP,
MEOW) is the product's surface, not decoration.

---

## dmux

<https://github.com/standardagents/dmux> — MIT, TypeScript/Node, 1,760 stars.

### Requirement 1 — PASS

Documented and specific, not a tagline. *"dmux supports attaching multiple git repositories to a
single tmux session, letting you manage panes, file browsers, and visibility controls across
different projects side by side"*; the sidebar *"organizes panes by project"*, each group showing the
project name and active pane count; `←`/`→` switch project groups, `↑`/`↓` move within a project, and
`P` **temporarily** collapses to one project and then restores all
([docs/src/content/multi-project.js](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/docs/src/content/multi-project.js)).
All-projects is the default view; single-project is the opt-in filter — the right way round. Panes
carry `projectRoot` on the pane record itself
([src/types.ts:54](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/types.ts#L54)),
and no project-scoped filter exists in the rendering path.

### Deletion policy — from source. **This is where dmux loses.**

**Every removal path force-removes. No lock is ever set. Nothing anywhere checks whether an agent
is attached.** `grep` for `worktree lock` across `src/` returns nothing.

The background cleanup service:

```ts
// src/services/WorktreeCleanupService.ts:84
    for (const target of worktreeRemovalTargets) {
      const removeResult = await this.runGitCommand(
        ['worktree', 'remove', target.worktreePath, '--force'],
        target.repoPath
      );
```

([src/services/WorktreeCleanupService.ts](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/services/WorktreeCleanupService.ts#L84))

`--force` is hardcoded, and a failure is logged as a warning, never surfaced as an error. Branch
deletion in the same job is `git branch -D`. The post-merge cleanup does the same
([src/utils/mergeExecution.ts:199](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/utils/mergeExecution.ts#L199)),
as does `deleteUnsavedChanges`
([src/hooks/useWorktreeActions.ts:180](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/hooks/useWorktreeActions.ts#L180)).

The one guard that exists is a **pane-count** check, not a liveness check. In `closeAction`, dmux
kills the tmux pane first and treats a surviving pane as a failed close — *"Failed to close pane
…; worktree cleanup was not started"* — then skips cleanup only if a **sibling pane shares the same
worktree path**
([src/actions/implementations/closeAction.ts:265-285](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/actions/implementations/closeAction.ts#L265)).
That is bookkeeping about dmux's own pane records, not a probe of whether an agent is running.

And the merge path is worse than the close path: `mergeWorktree` runs `git worktree remove` while
the pane is **still alive**, then shows a merge-confirmation dialog
([src/hooks/useWorktreeActions.ts:98](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/hooks/useWorktreeActions.ts#L98)).
`mergeAndPrune` goes further — it `git add -A && git commit -m 'chore: worktree changes'` on
whatever the agent left behind, merges, removes the worktree, then closes the pane
([same file, line 112](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/hooks/useWorktreeActions.ts#L112)).

Mitigating facts, stated fairly: every one of these paths is user-initiated from the pane menu —
there is **no background sweep**. `getOrphanedWorktreesAsync` finds worktrees with no active pane and
records `hasUncommittedChanges`, but it feeds branch **resumption**, not deletion
([src/utils/git.ts:275](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/utils/git.ts#L275)).
And `before_worktree_remove` / `worktree_removed` lifecycle hooks let you write your own guard
([src/utils/hooks.ts:25](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/utils/hooks.ts#L25)) —
which is you building the policy, not the tool having one.

**Does it force? Always. Does it set a lock? Never. Does it check for an attached agent? No.**

### The rest

- **Workspace at launch: PASS.** The pane bootstrap runs `git worktree add … -b <branch>` before
  building the agent launch command
  ([src/utils/paneBootstrapRunner.ts:498](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/utils/paneBootstrapRunner.ts#L498)).
  README: *"Press `n` … and dmux handles the rest — worktree, branch, and agent launch."*
- **Batch review: PASS.** No gate. Pane menu → Merge, or Create GitHub PR, per pane, whenever you
  like ([README.md](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/README.md)).
- **Tickets authored elsewhere: partial, and not documented as a feature.** A pane is created from a
  free-text prompt, so an issue body can be pasted in; the README notes you can *"provide an explicit
  branch/worktree name (useful for issue-tracker ticket naming)"*, and the config docs mention
  "non-interactive pane creation" using the default agent. But there is **no GitHub issue ingest** —
  checked all eleven docs pages under `docs/src/content/`, the README, and `src/index.ts`'s argument
  parsing (which handles only `--files-only` and remote pane-action shortcuts).
- **Direct to `main` with no PR: PASS.** Merge is a local `git merge <branch>` into the current
  branch; the GitHub PR path is a separate, optional menu item
  ([src/hooks/useWorktreeActions.ts](https://github.com/standardagents/dmux/blob/8cb3d926631a9349ab67f7ece41d218427ac7e24/src/hooks/useWorktreeActions.ts)).
- **Runs Claude Code: PASS.** Claude Code, Codex, OpenCode, Cline, Gemini, Qwen, Amp, pi, Cursor,
  Copilot and Crush CLIs, plus multi-select launches.
- **Platform: Linux fine.** tmux 3.0+, Node 18+, git 2.20+. macOS notifications are an extra, not a
  requirement; the docs give Linux clipboard equivalents.
- **Maintenance signal: the healthiest of the three.** Not archived, MIT, 32 open issues, created
  2025-08-20, last release **v5.11.1 on 2026-08-16** (the same day as the last push) with v5.11.0 the
  day before. Bus factor is real — `justin-schroeder` has 620 commits to the next contributor's 89 —
  but there is a genuine contributor tail. One oddity worth noting: the repo lives at
  `standardagents/dmux` while the README's issue link still points at `formkit/dmux`; the project has
  moved orgs and the README was not fully updated.

---

## OpenKanban

<https://github.com/TechDufus/openkanban> — AGPL-3.0, Go, 142 stars.

### Requirement 1 — PASS

Also provable from source, not just the README's *"Manage tickets across all your repositories from
one board."* Projects are registered git repos in a global registry
(`~/.config/openkanban/projects.json`), tickets are stored per project
(`~/.config/openkanban/tickets/{project_id}.json`), and a `GlobalTicketStore` *"aggregates tickets
from all projects"*
([ARCHITECTURE.md](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/ARCHITECTURE.md#L118)).
The board columns are populated from the global store, with the project filter opt-in:

```go
// internal/ui/model.go:2751
func (m *Model) refreshColumnTickets() {
	for i, col := range m.columns {
		allForStatus := m.globalStore.GetByStatus(col.Status)
		var filtered []*board.Ticket
		for _, t := range allForStatus {
			if !m.ticketMatchesFilter(t) { continue }
			...
}

func (m *Model) ticketMatchesFilter(t *board.Ticket) bool {
	if len(m.filterProjectIDs) > 0 && !m.filterProjectIDs[t.ProjectID] { return false }
	...
```

([internal/ui/model.go](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/internal/ui/model.go#L2751))

`@projectname` is a search prefix, and each ticket carries `ProjectID`. All repos, one board, by
default.

### Deletion policy — from source. **It fails, and its documentation is wrong about it.**

There is exactly one removal function and it hardcodes `--force`, then falls back to a raw
`os.RemoveAll`:

```go
// internal/git/worktree.go:98
func (m *WorktreeManager) RemoveWorktree(worktreePath string) error {
	cmd := exec.Command("git", "worktree", "remove", worktreePath, "--force")
	cmd.Dir = m.repoPath

	if output, err := cmd.CombinedOutput(); err != nil {
		if !strings.Contains(string(output), "not a working tree") {
			return fmt.Errorf("failed to remove worktree: %s: %w", string(output), err)
		}
	}

	if _, err := os.Stat(worktreePath); err == nil {
		if err := os.RemoveAll(worktreePath); err != nil {
			return fmt.Errorf("failed to remove worktree directory: %w", err)
		}
	}
	return nil
}
```

([internal/git/worktree.go](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/internal/git/worktree.go#L98))

**The documented `force_worktree_removal: false` default does not do what the docs say it does.**
`docs/CONFIGURATION.md` lists it as *"`force_worktree_removal` — Force removal even with uncommitted
changes"*, defaulting to `false`
([docs/CONFIGURATION.md](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/docs/CONFIGURATION.md#L112)).
In source it changes **only the wording of the confirmation prompt**. Both branches of the check call
the identical cleanup function:

```go
// internal/ui/model.go:2272
	if hasUncommitted && !m.config.Cleanup.ForceWorktreeRemoval {
		m.showConfirm = true
		m.confirmMsg = "Worktree has uncommitted changes. Force delete?"
		m.confirmFn = func() tea.Cmd { m.performTicketCleanup(ticket); return nil }
	} else {
		m.showConfirm = true
		m.confirmMsg = "Delete ticket: " + ticket.Title + "?"
		m.confirmFn = func() tea.Cmd { m.performTicketCleanup(ticket); return nil }
	}
```

([internal/ui/model.go](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/internal/ui/model.go#L2272))

And `performTicketCleanup` stops the ticket's terminal pane — killing the agent — and then force-
removes, with no reference to `AgentStatus` anywhere in the path
([internal/ui/model.go:2290](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/internal/ui/model.go#L2290)):

```go
	if pane, ok := m.panes[ticket.ID]; ok {
		pane.Stop()
		delete(m.panes, ticket.ID)
	}
	...
			if ticket.WorktreePath != "" && m.config.Cleanup.DeleteWorktree {
				err := mgr.RemoveWorktree(ticket.WorktreePath)
```

The confirmation dialog is the only guard — the same "prompt, not a liveness guard" that #486 called
out in repomon, with the extra twist that OpenKanban's config knob advertises a protection it does
not provide. OpenKanban does poll agent status on a timer (`pollAgentStatusesAsync`,
`tickAgentStatus`) and stores `AgentStatus` on every ticket — the signal exists and the delete path
simply never reads it.

**Does it force? Always, plus an `os.RemoveAll` fallback. Does it set a lock? Never. Does it check
for an attached agent? No — it kills it.**

There is no background sweep; deletion is user-initiated. That is the only mitigation.

### The rest

- **Workspace at launch: PASS.** The worktree is created when a ticket moves to In Progress, and
  `spawnAgent` refuses to run until the ticket is in that state — *"Press Space to move to In
  Progress first"*
  ([internal/ui/model.go:2466](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/internal/ui/model.go#L2466)).
  Worktree strictly precedes agent.
- **Batch review: PASS (vacuously).** There is no review machinery at all.
- **Tickets authored elsewhere: FAIL.** Tickets are created only in the TUI (`n`). The CLI has three
  commands — `openkanban new [name]`, `list`, `delete` — all of which operate on **projects**, not
  tickets ([cmd/root.go](https://github.com/TechDufus/openkanban/blob/02201ed231e37519541e9d92cd1e66316a7e97cb/cmd/root.go)),
  plus `config validate|generate|path`. A grep of `internal/` for `gh pr`, `pull request`, `github
  issue`, `import` and `merge` returns nothing but `mergeAgentDefaults`. There is no issue ingest,
  no PR creation and no merge feature anywhere in the product. A wayfinder issue would have to be
  retyped by hand, or written into `~/.config/openkanban/tickets/{project_id}.json` by a script you
  write — that file format is documented in `DATA_MODEL.md`, but scripted ticket creation is **not
  documented** as a supported path.
- **Direct to `main` with no PR: PASS (vacuously).** OpenKanban never merges or pushes anything.
  Landing is entirely yours, so `land` continues to work untouched — the flip side of having no
  ticket ingest either.
- **Runs Claude Code: PASS.** *"Any agent — OpenCode, Claude Code, Gemini, Codex, Aider, or whatever
  CLI tool you prefer"*, defined as arbitrary commands in config.
- **Platform: Linux fine.** Go, `brew install` documented for macOS **and** Linux, `go install`
  otherwise.
- **Maintenance signal: the weakest by a distance.** Not archived and no sunset notice, but: **one
  contributor** (`TechDufus`, 118 commits, and nobody else), last commit **2026-06-12**, last release
  **v0.1.1 on 2026-06-12** — the version number is still pre-1.0 after nine months. Six open issues.
  AGPL-3.0, the only copyleft licence of the three.

---

## Scoring table

| Line | Claude Code (incumbent) | Gas Town | dmux | OpenKanban |
|---|---|---|---|---|
| 1. 4-5 repos in one view | PASS (`claude agents --json`, verified on this machine in #485) | **PASS** — dashboard iterates all rigs from `rigs.json`; each rig is its own `git_url` | **PASS** — all attached repos grouped in one sidebar; single-project is the opt-in filter | **PASS** — `GlobalTicketStore` feeds every column; project filter opt-in |
| 2. Workspace at launch | **FAIL** — taken on first write | PASS — worktree, then `StartSession()` | PASS — `worktree add`, then agent launch | PASS — worktree on move to In Progress, before spawn |
| 3. Batch review (no per-ticket gate) | PASS | PASS — Refinery merge queue, no interactive gate | PASS — merge/PR per pane, on demand | PASS (no review machinery at all) |
| 4. Tickets authored elsewhere | PASS (GitHub issues today) | PASS — `bd github sync --pull-only`, then `gt sling` | Partial — paste the issue body as the prompt; no issue ingest | **FAIL** — TUI-only ticket creation, no CLI, no ingest |
| 5. Direct to `main`, no PR | PASS (`land`) | **FAIL** — *"polecats never push directly to main"*; Bors-style queue | PASS — local merge into `main` | PASS (it never lands anything, so `land` survives) |
| 6. Runs Claude Code (skills survive) | PASS | PASS | PASS | PASS |
| 7. Linux | PASS | PASS | PASS | PASS |
| **8. Deletion policy — liveness-aware?** | **PASS** — `git worktree lock` held for the run; sweep and `git worktree remove` both honour it | **PASS** — refuses on active tmux session in *both* the sweep and the manual remove; never sets a git lock, so out-of-band `git worktree remove` is unguarded | **FAIL** — `--force` hardcoded everywhere, no lock, no liveness check; the merge path removes the worktree with the pane still live | **FAIL** — `--force` hardcoded + `os.RemoveAll`, no lock, kills the agent's pane and deletes; `force_worktree_removal: false` protects nothing |
| Maintenance | Anthropic, current | Very active repo, but `main` last touched 2026-07-23, last release v1.2.1 2026-06-06 | Healthiest: v5.11.1 released 2026-08-16 | One contributor, last commit and release 2026-06-12, still v0.1.x |

---

## Bottom line

**Does any of these three beat staying on Claude Code? No — but Gas Town is the first candidate in
this entire survey that does not lose the deletion line.**

**dmux and OpenKanban are settled and they lose the same way repomon did.** Both win the
workspace-at-launch line. Both then hardcode `--force` on every worktree removal, never set a lock,
and never ask whether an agent is attached — OpenKanban goes further and kills the agent's terminal
on the way in, while advertising a `force_worktree_removal: false` setting that changes nothing but a
prompt string. This is exactly the trade #488 says is not worth making: *a tool that wins the
workspace-at-launch line and loses the deletion line is not an improvement.* dmux additionally has no
ticket ingest; OpenKanban has no ticket ingest, no PR, no merge, one contributor and a three-month-old
last commit. **Both rejected.**

**Gas Town is the interesting one, and it does not lose on deletion.** Its policy is liveness-aware
from source on both paths that matter: the automated sweep refuses to nuke a polecat whose tmux
session is alive (*"tmux is source of truth for liveness"*), and `gt polecat remove` refuses a running
session without `--force`, exactly as its docs claim. On top of that it blocks on uncommitted work,
blocks on stashes even under force, blocks on a pending merge-queue MR even in nuclear mode, blocks
when your shell is inside the worktree, and pushes unpushed commits before deleting. That is a
*richer* set of guards than Claude Code's. The one place Claude Code is still stronger: Gas Town
never sets a `git worktree lock`, so protection lives inside `gt` — a plain `git worktree remove`
typed by a human, or by `gt doctor --fix` on a stray crew worktree, is not stopped. Claude Code's
lock is enforced by git itself.

**So Gas Town wins two lines: the workspace at launch, and roughly a draw-to-better on deletion.
Here is what it costs.**

1. **`land` dies.** *"Polecats never push directly to main"* is a design statement, not a setting.
   Landing becomes the Refinery's Bors-style merge queue. Requirement 5 is a hard fail, and #481/#482
   (what `land` and `pushpr` become) would be answered by deleting them and adopting `gt done`.
2. **GitHub issues stop being the tracker of record.** Beads becomes it. `bd github sync --pull-only`
   makes wayfinder issues importable, so this is a bridge rather than a wall — but wayfinder's map
   would then live in two places, and a worked multi-repo GitHub-sync configuration is not documented.
3. **The infrastructure is enormous.** A town runs a Dolt SQL server, a daemon, a Mayor, a Deacon and
   its Dogs, plus a Witness and a Refinery per rig — every one of them a tmux-hosted agent session
   burning tokens. Against a workflow whose current defect is "the worktree is taken slightly late",
   this is a very large machine bought for a very small fix, and #478 already has a workaround for
   that defect.
4. **The maintenance headline is softer than the star count.** No commit on `main` since 2026-07-23,
   no release since v1.2.1 on 2026-06-06, and 4,831 of the commits belong to one person.

**Recommendation: stay on Claude Code.** #485's and #486's conclusion survives contact with all three
missed candidates. Gas Town is the only one worth re-examining, and only if the map's priorities
change — if orchestrating many agents across many repos ever outweighs keeping `land`, keeping GitHub
issues, and keeping the setup small. On today's requirements it fails requirement 5 outright and buys
requirement 2 at a price out of all proportion to the defect.

**The one thing worth stealing regardless of the decision:** Gas Town's `assessStaleness` shows that
a liveness guard does not have to be a `git worktree lock`. *"If session is active, not stale"* — a
cheap `tmux has-session` probe, backed by a heartbeat file with a stale threshold and a PID fallback
that fails closed on any transient error — is a design our own sweep could copy directly, and it
guards a case the lock does not: an agent that is alive but whose lock was released.

---

## Could not determine

Recorded as gaps, not guesses.

- **Gas Town — what the flow becomes with `merge_queue.enabled: false`.** The field is documented
  with a default of `true`; the consequence of disabling it is not. Checked `docs/reference.md`
  (merge-queue field table and Agent Lifecycle), `README.md` (Merge Queue / Refinery section),
  `docs/CLEANUP.md`.
- **Gas Town — a worked multi-repo GitHub-sync setup.** `bd github sync` is configured with a single
  `github.owner`/`github.repo` pair; `RigEntry.BeadsConfig` implies per-rig configs, but no example
  covering several GitHub repos in one town was found in the beads CLI reference or the Gas Town
  docs tree.
- **dmux — non-interactive pane creation.** The configuration docs reference it in passing (the
  default agent is *"used for non-interactive pane creation"*), but no flag, syntax or example
  appears in the eleven docs pages, the README, or `src/index.ts`'s argument handling.
- **OpenKanban — scripted ticket creation.** The on-disk ticket JSON is documented in
  `DATA_MODEL.md`, so writing tickets from a script is clearly possible, but it is nowhere endorsed
  as a supported interface, and nothing validates or reloads externally written files on a schedule.
