# The eight the curated indexes missed

Extends [#485](https://github.com/caneff/agent-skills/issues/485) (shortlist),
[#486](https://github.com/caneff/agent-skills/issues/486) (breadth sweep, plus its correction
comment) and [#488](https://github.com/caneff/agent-skills/issues/488) (the three the sweep missed).

#485 and #486 concluded "nothing beats staying on Claude Code". Their rejection reasoning was read
from source and it stands. Their *candidate lists* came from two curated "awesome" indexes; a
GitHub search-API enumeration has since shown the field is several times larger. These eight were
never scored. Nothing already scored in #485/#486/#488 is re-scored here.

Every project below was cloned and read at a pinned commit. No roundups, no third-party reviews,
no relayed facts. Where a fact is absent from primary sources it is written "not documented" with
the list of what was checked.

| Project | Commit read | Default-branch HEAD date | Clone |
|---|---|---|---|
| cc-haha | `a78b4e73ced4f3ca42e04f051226342e469a5b05` | 2026-08-23 | <https://github.com/NanmiCoder/cc-haha> |
| agent-orchestrator | `2bada3983f294c201578f32463fe0a140e650590` | 2026-09-01 | <https://github.com/Untrivial-ai/agent-orchestrator> |
| worktrunk | `cf3c67b03b695ab0c73221cd3b8580f2c0758a57` | 2026-09-01 | <https://github.com/max-sixty/worktrunk> |
| 1code | `9f1bc76fa4372c18c565b5a4f8daf38ae3595f0e` | 2026-02-24 | <https://github.com/21st-dev/1code> |
| supacode | `257ebe1bb6d1fa84c79e45c10957ce479c008eaa` | 2026-08-26 | <https://github.com/supabitapp/supacode> |
| native-cli-ai (`nca`) | `2268932edeaf4b18c8c8e9548411723bbe1328fb` | 2026-07-12 | <https://github.com/madebyaris/native-cli-ai> |
| orca | `5aa02ead59a4f34a186c3e8814558b5795260ee9` | 2026-09-01 | <https://github.com/stablyai/orca> |
| forge (`kenn-forge`) | `b2b8a59a2bbd0555ad699f4bd53524a330b8eb81` | 2026-08-31 | <https://github.com/kenn-io/forge> |

---

## The bar

Claude Code wins today because it loses exactly one line — the workspace is taken on first write
rather than at launch — and because its deletion policy is lock-based and liveness-aware: it holds a
`git worktree lock` for the whole run, and both its sweep and `git worktree remove` honour that
lock. #486 proved repomon will remove a clean worktree with a live agent attached; #488 proved dmux
hardcodes `--force` at three call sites and OpenKanban ships a `force_worktree_removal` flag whose
two branches assign the identical handler. **Winning the workspace-at-launch line while losing the
deletion line is not an improvement.**

This round is the first in which that bar is cleared — twice.

---

## A correction that changes how the deletion line is read

Every prior round treated "hardcodes `--force`" as equivalent to "will delete a live agent's
worktree". Read against git's own documentation, that is too strong by one step.

From `git help worktree`, on `remove --force`:

> `-f`, `--force` … **To remove a locked worktree, specify `--force` twice.**

A single `--force` overrides only git's *dirty* refusal. It does **not** override a
`git worktree lock`. So a tool that hardcodes one `--force`, sets no lock of its own, and checks no
liveness will still be stopped by *Claude Code's* lock, for as long as Claude Code holds it. What
such a tool actually destroys is:

1. a worktree whose agent is alive but whose lock has already been released, and
2. a worktree it deletes by a path that is not `git worktree remove` at all — an `os.RemoveAll`,
   an `rm -rf`, or a directory rename.

Both of those turn up below. The distinction is what separates a candidate that is merely careless
(cc-haha) from one that is actively destructive (forge, and Agent Orchestrator's one hole).

No candidate in these eight passes `--force` twice for a removal. Orca passes `-f -f` in one place,
and it is a `git worktree move`, not a remove
([`src/main/git/worktree-create-preparation.ts:224`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/git/worktree-create-preparation.ts#L224)),
with the comment *"`-f -f` moves the locked preparation while preserving its lock reason (Git >=2.25)"*.

---

## The four cheap rejects

Applied first, stopping at the first failure, exactly as the method requires.

### 1code — **dead** (reject b)

The repository is **archived** on GitHub (`"archived": true` from `GET /repos/21st-dev/1code`).
The default branch's HEAD is `9f1bc76` *"Release v0.0.72"*, dated **2026-02-24**; the newest
release is **v0.0.84, 2026-03-06**. Six months with no commit on `main` and an archive flag is the
end of the check — a `pushed_at` of 2026-03-06 is branch churn, not life.

There is **no explicit sunset notice** in the README (checked `README.md` in full — its 40-line
highlights block still advertises the product in the present tense). The archive flag is the
notice.

Scored no further. Worth recording that it *would* have been interesting: "Git Worktree Isolation —
each chat runs in its own isolated worktree" plus a Kanban board is the right shape.

### supacode — **macOS-only** (reject a)

Its own README, first line under the title:

> **A native macOS command center for running coding agents in parallel.**

Confirmed from the build definition rather than the tagline. Every target in `Project.swift`
declares `destinations: .macOS`, at lines 122, 187, 212, 225, 251, 274 and onward, with
`deploymentTargets: .macOS("26.1")` for the app
([`Project.swift`](https://github.com/supabitapp/supacode/blob/257ebe1bb6d1fa84c79e45c10957ce479c008eaa/Project.swift#L122)).
It is a Tuist/Swift/AppKit project with no non-Darwin destination anywhere. The user is on
Windows/WSL2. Out.

### native-cli-ai (`nca`) — **brings its own agent** (reject c)

`nca` is not an orchestrator that runs Claude Code. It is itself a coding agent with its own model
loop. Its README:

> `nca` is a Rust-native coding CLI that ships as a single binary… interactive TUI, line REPL,
> one-shot runs, detached sessions…
>
> **Providers** — MiniMax is the default provider path. The codebase also supports OpenAI,
> Anthropic, and OpenRouter…

The word "Claude" appears in the source **only** as an API model id — `crates/runtime/src/model_limits.rs`
matches `claude-3-7`, `claude-3-5`, `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku` for context-window
detection, and `crates/common/src/config.rs:997` maps the string `"claude"` to
`Provider::Anthropic`. There is no spawn of a `claude` binary anywhere in `crates/` or `docs/`.

Its description ("orchestrating AI agents **across projects**, with persistent sessions, worktrees,
and local-first control") is the requirement verbatim, which is why it was on the list — but the
"agents" it orchestrates are its own subagents against its own provider, not the user's Claude
Code. The skills and hooks would not survive; they would have nothing to survive into.

Also near-dead on its own terms: default-branch HEAD **2026-07-12**, 194 stars, no licence file,
one contributor.

### worktrunk — **one repo per view** (reject d)

This one hurts, because worktrunk is the best-engineered tool in this survey and its deletion
policy is the best of the eight. It fails requirement (d), and it fails it from source rather than
from a tagline.

`wt list` is scoped to a single repository. The collection pipeline opens exactly one
`Repository` discovered from the current directory and enumerates it with `git worktree list
--porcelain`:

> | 4 | `git worktree list --porcelain` | [`Repository::list_worktrees`] | Path, HEAD SHA, branch, and flags per worktree — **the row source for the skeleton**.

([`src/commands/list/collect/mod.rs:27`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/commands/list/collect/mod.rs#L27))

The JSON schema confirms the scope from the other end: *"Top-level `repo` describes **the local
checkout's** repository as derived from the primary remote"*
([`docs/src/content/docs/list.md:439`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/docs/src/content/docs/list.md#L439)).

And worktrunk says outright that another repository's checkout is invisible to it:

```rust
// src/git/repository/tests.rs:1583
// Somebody's checkout, which `list_worktrees` cannot see because it belongs
// to another repository. worktrunk gathers every repo and worktree into one
// parent, so a sibling is one `../` from any command, and calling a live
// one "not a worktree" reads as an invitation to delete it.
```

([`src/git/repository/tests.rs:1583`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/git/repository/tests.rs#L1583))

A grep of `docs/`, `README.md` and `src/` for *multiple repositor*, *across repositor*,
*multi-repo* and *all repositor* returns only config-scope prose ("user hooks … for all
repositories") — never a cross-repo view. There is no `--all-repos` flag. Five repos means five
`cd`s. **Out on (d).**

**Recorded anyway, because it is worth stealing: worktrunk has the strongest worktree-deletion
hygiene of the eight, and it is the only one that honours the lock *as a hard error to the user*.**

- `Repository::remove_worktree(path, force)` passes `--force` only when the caller asks, or when it
  synthesises one for a submodule worktree — and in the synthesised case it **re-runs
  `ensure_clean()` immediately before the destructive command**, "restoring the backstop git would
  otherwise have provided", inside a registry write-lock critical section so a concurrent writer
  cannot dirty the tree in the gap
  ([`src/git/repository/worktrees.rs:286`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/git/repository/worktrees.rs#L286)).
- A locked worktree is a terminal error with no escape hatch inside `wt`:
  `GitError::WorktreeLocked` renders *"Cannot remove **{branch}**, worktree is locked{reason}"* with
  the hint *"To unlock, run `git worktree unlock <path>`"*
  ([`src/git/error.rs:833`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/git/error.rs#L833),
  [`:1281`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/git/error.rs#L1281)).
  A grep of `src/` for `"unlock"` as a git argument returns **nothing** — worktrunk never unlocks
  anything, so `wt remove --force` cannot walk past a Claude Code lock either.
- `stage_worktree_removal` runs an **ownership check before** the dirty gate and *outside* the
  branch `--force` skips, with the reasoning written down: *"`--force` is the user waiving their own
  uncommitted changes, never a claim about who owns the directory, so it cannot be allowed to skip
  it"*
  ([`src/git/remove.rs:427`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/git/remove.rs#L427)).
- The one sharp edge, and it is opt-in: `wt remove --reap` (experimental, Unix-only) **kills** every
  process whose cwd is under the worktree — `reap::collect_reapable` then `reap::reap_pids`
  (SIGTERM→SIGKILL), best-effort, with the controlling terminal and self excluded
  ([`src/commands/remove.rs:189`](https://github.com/max-sixty/worktrunk/blob/cf3c67b03b695ab0c73221cd3b8580f2c0758a57/src/commands/remove.rs#L189)).
  That is the opposite of a liveness guard, but it is a flag the user types, it runs *after* the
  removal succeeded, and the lock still gates the removal.

---

## The four survivors

### cc-haha (Claude Code Haha)

<https://github.com/NanmiCoder/cc-haha> — MIT, TypeScript/Electron, 14,259 stars.

#### Platform: Linux fine

> Claude Code Haha is a **desktop Claude Code workspace** for macOS, Windows, and Linux

([`README.md:25`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/README.md).
The pinned HEAD commit is *"feat(release): sign Windows artifacts with SignPath"*.)

#### Requirement (c) — this is a **fork of Claude Code**, not a launcher of it

This is the single most important fact about cc-haha and it is not in the description. Its
`package.json` reads:

```json
{
  "name": "claude-code-local",
  "version": "999.0.0-local",
  "bin": { "claude-haha": "./bin/claude-haha" }
}
```

([`package.json:2`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/package.json))

`src/` is a vendored, extended copy of the Claude Code CLI's own tree — `QueryEngine.ts`,
`query.ts`, `Tool.ts`, `tools.ts`, `src/tools/AgentTool/`, `src/tools/ExitWorktreeTool/`, and
telemetry events still named `tengu_*`. The desktop app ships and runs `claude-haha`, its own
binary. It does not spawn the user's installed `claude`.

**Does that fail reject (c)?** Not on the requirement as written — *"the user's skills and hooks
must survive"* — because the fork reads the same configuration the user already has:

- hooks: `src/utils/hooks.ts` handles `PreToolUse`, `UserPromptSubmit`, `SessionStart` and the rest
  ([`src/utils/hooks.ts:89`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/hooks.ts#L89));
- skills: `getSkillsPath('userSettings', 'skills')` resolves `~/.claude/skills`, and the change
  detector also watches `~/.agents/skills`, `<project>/.agents/skills` and `<project>/.claude/skills`
  ([`src/utils/skills/skillChangeDetector.ts:181`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/skills/skillChangeDetector.ts#L181));
- settings: `~/.claude/settings.json` and `~/.claude.json` are read for `apiKeyHelper`, CA certs,
  cloud auth and more (`src/utils/auth.ts`, `src/utils/caCertsConfig.ts`).

So it is **PASS with a large asterisk**: the agent that runs the user's skills is a third party's
fork pinned to whatever Claude Code version it vendored, updated on that maintainer's schedule, not
Anthropic's. That is a supply-chain and drift cost that no other survivor here carries.

#### Requirement (d) — **PASS**, from source

The desktop sidebar lists **every** session across **every** project, grouped by project. The store
action takes an optional filter:

```ts
// desktop/src/stores/sessionStore.ts:266
function buildSessionListParams(project: string | undefined) {
  return project
    ? { project, limit: SESSION_LIST_LIMIT }
    : { limit: SESSION_LIST_LIMIT }
}
```

([`desktop/src/stores/sessionStore.ts:266`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/desktop/src/stores/sessionStore.ts#L266))

and **every production call site passes no project** — `fetchSessions()` at
`sessionStore.ts:130`, `:164`, `Sidebar.tsx:1096`, `:1599`, `features/pets/PetApp.tsx:118`, `:182`.
The tab-restore path is likewise unfiltered: `sessionsApi.list({ limit: 200 })`
([`desktop/src/stores/tabStore.ts:475`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/desktop/src/stores/tabStore.ts#L475)).
The sidebar then groups with `groupByProject(...)` and comments on the intent:

```ts
// desktop/src/components/layout/Sidebar.tsx:238
// Title filtering moved into the global search modal (Cmd+K); the list shows all sessions.
const filteredSessions = sessions
```

([`desktop/src/components/layout/Sidebar.tsx:238`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/desktop/src/components/layout/Sidebar.tsx#L238))

All-projects is the construction; per-project would have to be added. 4–5 repos in one sidebar, one
window, one click to switch. **PASS.**

#### Deletion policy — from source

**Four hardcoded single-`--force` removal call sites; no `git worktree lock` is ever set; no
attached-agent check anywhere.**

```ts
// src/utils/worktree.ts:1194  (removeAgentWorktree)
      ['worktree', 'remove', '--force', worktreePath],
```

and identically at
[`src/utils/worktree.ts:487`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/worktree.ts#L487),
[`:994`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/worktree.ts#L994) and
[`src/utils/swarm/teamHelpers.ts:584`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/swarm/teamHelpers.ts#L584).
A grep of `src/` for every array literal containing `'worktree',` returns exactly `add`, `remove
--force` ×4, `prune`, and `list --porcelain` — **`lock` is not among them.** The fork does not set
the lock its upstream is credited with.

**The background sweep.** `cleanupStaleAgentWorktrees` runs from `cleanup.ts:595` on a
**30-day** cutoff (`DEFAULT_CLEANUP_PERIOD_DAYS = 30`, overridable via `settings.cleanupPeriodDays`,
[`src/utils/cleanup.ts:23`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/cleanup.ts#L23)).
It is documented as fail-closed and the code matches the docstring
([`src/utils/worktree.ts:1246`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/utils/worktree.ts#L1246)):

- only slugs matching `EPHEMERAL_WORKTREE_PATTERNS` (`agent-a<7hex>`, `wf_*`, `bridge-*`, `job-*`) —
  never a user-named worktree;
- skips `currentWorktreeSession?.worktreePath` — **its own** session only;
- skips unless `mtime < cutoff`;
- skips unless `git status --porcelain -uno` exits 0 **and** is empty;
- skips unless `git rev-list --max-count=1 HEAD --not --remotes` exits 0 **and** is empty (nothing
  unpushed);
- non-zero exit on either probe means skip — *"we don't know what's in there"*.

**Verdict: worse than Claude Code, but the weakest failure in this survey series.** There is no
liveness probe of any kind; the only thing standing between a *second* live agent's worktree and
deletion is that it must be clean, fully pushed, and untouched for 30 days. In practice a live
agent's worktree has a recent mtime, so the mtime cutoff acts as a crude liveness proxy — which is
an accident of the design, not a guard. And because the sweep is the only automated path, and every
manual path is a single `--force`, an *upstream* Claude Code lock (if one is held by a sibling
process) would still stop it. It never destroys unpushed work.

#### The rest

- **Workspace at launch: PASS.** The new-session UI offers "Isolated worktree" as a launch-time card
  ([`desktop/src/components/chat/RepositoryLaunchControls.tsx:796`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/desktop/src/components/chat/RepositoryLaunchControls.tsx#L796)),
  and the server runs `prepareSessionWorkspace(...)` → `createDesktopWorktree` → `git worktree add
  -b <branch> <path> <baseRef>`
  ([`src/server/services/repositoryLaunchService.ts:665`](https://github.com/NanmiCoder/cc-haha/blob/a78b4e73ced4f3ca42e04f051226342e469a5b05/src/server/services/repositoryLaunchService.ts#L665))
  from `conversationService.ts:380`, before the conversation starts. Worktree strictly precedes agent.
- **Batch review: PASS.** The workspace lists a turn's changed files with a full-width diff and a
  whole-turn undo; there is no mandatory per-ticket interactive gate.
- **Tickets authored elsewhere: FAIL as a product feature, PASS in practice.** A grep of `src/` and
  `desktop/src/` for `api.github.com`, `octokit`, `gh issue list` and `issue.*import` returns only
  an upstream-proxy allow-list entry and a read-only-command classifier that recognises
  `gh issue list`. There is **no issue browser, no issue ingest, no PR view** in the product. The
  agent's own shell still runs `gh issue view`, exactly as today — which is the status quo, not an
  improvement.
- **Direct to `main` with no PR: PASS.** cc-haha never merges or pushes on the user's behalf; a grep
  for PR creation in `desktop/src/api/` returns nothing. `land` is untouched.
- **Maintenance signal: healthy headline, severe bus factor.** 14,259 stars, MIT, not archived, 182
  open issues. Default-branch HEAD **2026-08-23**; latest release **v0.5.5, 2026-08-22**; the
  `pushed_at` of 2026-09-01 is branch churn. Contributors: `NanmiCoder` **1,746** commits, next
  highest **19**. One person, and the product is a fork of someone else's agent.

---

### Agent Orchestrator (AO)

<https://github.com/Untrivial-ai/agent-orchestrator> — Apache-2.0, Go backend + Electron/React
frontend, 10,809 stars.

#### Platform: Linux fine

Ships `linux-x64.AppImage`, `.deb` and `.rpm` alongside macOS and Windows builds
([`README.md`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/README.md) install table).

#### Requirement (c) — runs the user's Claude Code: **PASS**

> **26 coding agents supported** through one supervised workflow.

with Claude Code first in the table, run as its native terminal UI inside a tmux/conpty runtime
(`docs/architecture.md:3`). AO supplies no model loop of its own; the "orchestrator" is itself one
of the supervised agents.

#### Requirement (d) — **PASS on the switching clause, and better than that on one axis**

Two separate findings, and they point in different directions. Both are from source.

**The Kanban board is per-project.** `SessionsBoard` takes an optional `projectId` and the comment
says what that means:

```tsx
// frontend/src/renderer/components/SessionsBoard.tsx:56
	/** When set, the board shows only this project's sessions. */
	projectId?: string;
…
	const workspaces = projectId ? all.filter((workspace) => workspace.id === projectId) : all;
```

([`frontend/src/renderer/components/SessionsBoard.tsx:56`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/frontend/src/renderer/components/SessionsBoard.tsx#L56))

An all-projects board is therefore *representable* — and it is not routed. The only mount passes a
project: `_shell.projects.$projectId.tsx:10` renders `<SessionsBoard projectId={projectId} />`, and
the index route renders `HomePage`, which is a list of **projects** with session counts, not a
merged board (`frontend/src/renderer/components/HomePage.tsx:64`). So there is no single Kanban
showing 4–5 repos' cards at once.

**The sidebar is global.** It is a tree of every registered project, each expandable to its
sessions, in one window, with disclosure state persisted per project ID
([`frontend/src/renderer/components/Sidebar.tsx:452`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/frontend/src/renderer/components/Sidebar.tsx#L452)),
and the backend list endpoint's project filter is optional
(`filter := sessionsvc.ListFilter{ProjectID: domain.ProjectID(q.Get("project"))}` —
[`backend/internal/httpd/controllers/sessions.go:1604`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/httpd/controllers/sessions.go#L1604)).
Switching between running agents across repos is one click, one window. **PASS on the switching
clause** — the same standing #486 gave Nimbalyst, but proven from the routed component rather than
a FAQ.

**And a third thing no prior candidate has: one session can span several repos.** A project has a
`Kind`:

```go
// backend/internal/domain/project.go:8
	// ProjectKindWorkspace is a parent root-as-repo plus child repositories.
	ProjectKindWorkspace ProjectKind = "workspace"
```

([`backend/internal/domain/project.go:8`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/domain/project.go#L8))

and on spawn, a workspace project enumerates its child repos and gives the **one** session a
worktree in **each**:

```go
// backend/internal/session_manager/manager.go:1056
	if project.Kind.WithDefault() == domain.ProjectKindWorkspace {
		repos, err := m.store.ListWorkspaceRepos(ctx, project.ID)
		…
			targets = append(targets, defaultBranchRefreshTarget{
				repoPath:         filepath.Join(project.Path, filepath.FromSlash(repo.RelativePath)),
				configuredBranch: repo.DefaultBranch,
			})
```

([`backend/internal/session_manager/manager.go:1056`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/session_manager/manager.go#L1056))

Teardown iterates the same `rows []ports.WorkspaceRepoInfo` in reverse. **Constraint, from the
source:** the child repos must be nested under one parent directory (`filepath.Join(project.Path,
repo.RelativePath)`); arbitrarily-located repos cannot form one workspace project.

#### Deletion policy — from source. **This is the second-best policy found in any of these rounds.**

AO splits removal into two named operations and the split is enforced by comments that read like a
design document.

**`Destroy` — the default, lock-honouring, dirty-refusing path.** It deliberately omits `--force`:

```go
// backend/internal/adapters/workspace/gitworktree/commands.go:49
// worktreeRemoveArgs intentionally omits --force: a dirty worktree (uncommitted
// agent work) MUST cause `git worktree remove` to fail, so the post-prune
// "still registered" check in Destroy surfaces the refusal to the Session
// Manager's Cleanup, which routes the session to Skipped rather than deleting
// the agent's in-progress changes.
func worktreeRemoveArgs(repo, path string) []string {
	return []string{"-C", repo, "worktree", "remove", path}
}
```

([`backend/internal/adapters/workspace/gitworktree/commands.go:49`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/adapters/workspace/gitworktree/commands.go#L49))

and `Destroy` classifies a lock refusal explicitly rather than swallowing it:

```go
// backend/internal/adapters/workspace/gitworktree/workspace.go:392
	if _, ok := findWorktree(records, path); ok {
		if removeErr != nil {
			if isLockedWorktreeRemoveError(removeErr) {
				return fmt.Errorf("gitworktree: refusing to remove %q: path is still registered after git worktree prune (worktree remove: %w)", path, removeErr)
			}
```

with

```go
// backend/internal/adapters/workspace/gitworktree/workspace.go:1229
func isLockedWorktreeRemoveError(err error) bool {
	return strings.Contains(err.Error(), "cannot remove a locked working tree")
}
```

([`workspace.go:392`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/adapters/workspace/gitworktree/workspace.go#L392),
[`:1229`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/adapters/workspace/gitworktree/workspace.go#L1229))

A failed *dirty probe* is also an error, not a pass — *"A failed probe must stay visible: without it
the caller can't tell 'not dirty' from 'couldn't check'"* (`workspace.go:403`). Fail-closed.

**The automated cleanup only touches terminated sessions, and refuses on an open terminal.**

```go
// backend/internal/session_manager/manager.go:3338
	for _, rec := range recs {
		if !rec.IsTerminated {
			continue
		}
```

and per session:

```go
// backend/internal/session_manager/manager.go:3370
	release, closeErr := m.beginShellTerminalTeardown(ctx, rec.ID)
	if closeErr != nil {
		m.logger.Warn("cleanup: shell terminal still open", "sessionID", rec.ID, "error", closeErr)
		return "shell terminal still open"
	}
```

*"a non-empty reason means it was left alone this run … most commonly because a scoped shell
terminal could not be confirmed closed, so reclaiming would pull the ground out from under it"*
([`manager.go:3364`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/session_manager/manager.go#L3364)).
The sweep then calls `Destroy`, never `ForceDestroy`.

**`ForceDestroy` — used only after the work has been captured.** Its own docstring gates it:

```go
// backend/internal/adapters/workspace/gitworktree/workspace.go:419
// ponytail: only safe to call AFTER the session's uncommitted work has been
// captured via StashUncommitted. Calling it before capture silently
// discards agent work. For interactive teardown (ao session kill, ao cleanup)
// use Destroy, which refuses dirty worktrees via ErrWorkspaceDirty.
```

All four call sites obey it — `manager.go:1719`, `:1798`, `:2222`, `:2893` — and every one runs
`StashUncommitted` → `runtime.Destroy` (kill the agent) → `ForceDestroy`, in that order.
`StashUncommitted` captures tracked edits *and* new non-ignored files into a commit object at
`refs/ao/preserved/<session-id>` **without mutating the working tree or the stash stack**
(`workspace.go:452`). Nothing is lost even on the force path. No other candidate in any round does
this.

**The one real hole, and it is the `os.RemoveAll` kind.** `ForceDestroy` passes a *single*
`--force` — which cannot defeat a `git worktree lock` — and then deletes the directory anyway:

```go
// backend/internal/adapters/workspace/gitworktree/workspace.go:439
	// --force bypasses git's dirty check; errors here are advisory (the path may
	// already be gone). We proceed to prune regardless.
	_, _ = w.run(ctx, w.binary, worktreeForceRemoveArgs(repo, path)...)
	…
	// os.RemoveAll as a backstop: cleans up filesystem residue left behind if
	// git worktree remove --force still left the directory
	if err := removeAllWithRetry(ctx, path); err != nil {
```

([`workspace.go:439`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/adapters/workspace/gitworktree/workspace.go#L439))

The git error is discarded (`_, _ =`), so a *locked* worktree fails the git remove silently and the
`os.RemoveAll` runs regardless. Against a Claude Code lock this is the one path in AO that walks
through it. Mitigating: it fires only on explicit teardown paths, only after the agent's runtime
has been destroyed on the line above, and only after the work is preserved to a ref.

**Does it force? Does it set a lock? Does it check for an attached agent?**
Forces only on named force paths, never in the sweep; **never sets a `git worktree lock`** (a grep
of `backend/` for `worktree", "lock` returns nothing — only `remove`, `remove --force`, `prune`,
`add`); checks *session termination* and *open-terminal* liveness rather than process liveness. A
`processalive.Alive(pid)` helper exists (`backend/internal/processalive/process_unix.go`, EPERM
counts as alive, zombies do not) but is used for the daemon and chat host, not the deletion path.

#### The rest

- **Workspace at launch: PASS.** `docs/architecture.md:258` sequences `Mgr->>WS: Create(project,
  branch)` before `Mgr->>ChatSvc: StartChat(session, worktree, harness)`; source matches at
  `manager.go:1122` (`m.workspace.Create(...)` inside `createSessionWorkspace`, called before the
  runtime is started).
- **Batch review: PASS.** The Kanban's *In review* / *Ready to merge* columns are derived from PR,
  CI and reviewer facts (`backend/pkg/contract/kanban.go`); nothing forces an interactive gate per
  ticket. There is an `autoreview` package for agent reviews, opt-in.
- **Tickets authored elsewhere: PASS, first-class.** AO has a real issue-tracker port:
  `TrackerProviderGitHub` / `TrackerProviderGitLab`, a normalized issue-state vocabulary, and
  adapters under `backend/internal/adapters/tracker/{github,gitlab,multi}`
  ([`backend/internal/domain/tracker.go:15`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/domain/tracker.go#L15)).
  `SpawnConfig.IssueID` makes a worker spawnable **against a GitHub issue**, whose body is fetched
  and injected as context, capped at 12,000 chars
  ([`backend/internal/service/session/issue_context.go:16`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/internal/service/session/issue_context.go#L16)).
  A wayfinder issue goes straight in.
- **Direct to `main` with no PR: PASS mechanically, awkward in the UI.** Nothing in AO forces a PR;
  the worker owns "implementation, tests, commits, and pull requests" and has a real shell in its
  worktree, so `land` runs unchanged. But the board is PR-derived — *"KanbanBuilding is a session
  with no PR yet"*
  ([`backend/pkg/contract/kanban.go:13`](https://github.com/Untrivial-ai/agent-orchestrator/blob/2bada3983f294c201578f32463fe0a140e650590/backend/pkg/contract/kanban.go#L13))
  — so a session that lands to `main` without ever opening a PR **never leaves the Building
  column**. The operational view the product sells is the part that stops working.
- **Maintenance signal: the strongest of the eight on breadth.** 10,809 stars, Apache-2.0, not
  archived, 850 open issues. Default-branch HEAD **2026-09-01**; releases are near-daily
  (`v0.12.10` stable 2026-08-31, nightlies twice a day). Six-plus human contributors with a real
  distribution (436 / 234 / 209 / 172 / 161 / 85) — no bus factor, unlike every other candidate in
  this survey series.
- **WSL2 caveat, recorded honestly: not documented.** AO ships a Linux AppImage/deb/rpm and a
  Windows exe. Whether the Windows build can drive repositories that live *inside* a WSL2 distro is
  **not documented** — a grep of `backend/`, `frontend/src/` and `docs/` for `wsl` returns nothing.
  Running the Linux build under WSLg is plausible and untested. Orca, below, does document this.

---

### Orca

<https://github.com/stablyai/orca> — MIT, TypeScript/Electron, **58,917 stars** (the ticket's
figure was stale by an order of magnitude).

#### Platform: Linux fine — **and WSL is first-class**

The README badge reads `macOS | Windows | Linux` with builds for all three. More to the point for
this map, Orca has a whole WSL subsystem: `src/main/wsl/wsl-runner.ts`,
`wsl-guest-environment.ts`, `wsl-invocation-boundary.test.ts`, `wsl-probe-failure-semantics.test.ts`,
`shared/wsl-paths.ts` (`parseWslUncPath`), and `src/main/git/wsl-linked-worktree-git-routing.ts`.
The deletion code branches on it explicitly:

```ts
// src/main/git/worktree-removal.ts:114
  // Why: WSL-owned checkouts are deleted inside the distro, so Node on Windows must not rename them.
  if (options.wslDistro || parseWslPath(worktreePath)) {
    return false
  }
```

([`src/main/git/worktree-removal.ts:114`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/git/worktree-removal.ts#L114))

This is the only candidate across #485, #486, #488 and this round that has thought about
Windows-host-driving-WSL-guest repositories at all. It is the user's exact environment.

#### Requirement (c) — runs the user's Claude Code: **PASS**

> Works with **any CLI agent** — if it runs in a terminal, it runs in Orca.

Confirmed from source: Orca does not vendor an agent, it *instruments* one. `src/main/claude/`
contains only a hook service, hook settings, a statusline script and transcript readers — no model
loop. It installs managed hooks into the user's `~/.claude/settings.json` for `SessionStart`,
`UserPromptSubmit`, `Stop`, `StopFailure` and teammate lifecycle events, tagged so they can be
removed again (`removeManagedCommands`), and it is careful about single-slot settings — *"statusLine
is a single settings slot, not a hooks array — never overwrite a…"*
([`src/main/claude/hook-settings.ts:239`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/claude/hook-settings.ts#L239)).
It installs **no `PreToolUse` hook**, so the user's `rtk`, require-worktree and block-dangerous-git
hooks are untouched.

**Recordable cost:** it writes to `~/.claude/settings.json`. That file is the user's, and a second
writer on it is a new risk even when the merge is additive.

#### Requirement (d) — **PASS**

The renderer keeps a flattened, cross-repo worktree index:

```ts
// src/renderer/src/store/worktree-repo-index.ts:9
type WorktreeSnapshot = {
  allWorktrees: Worktree[]
  worktreeMap: Map<string, Worktree>
  worktreesById: Map<string, Worktree[]>
}
…
export function getIndexedAllWorktrees(worktreesByRepo: AppState['worktreesByRepo']): Worktree[]
```

([`src/renderer/src/store/worktree-repo-index.ts:9`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/renderer/src/store/worktree-repo-index.ts#L9))

and the sidebar renders one worktree list grouped into project lanes across every registered repo:
`src/renderer/src/components/sidebar/worktree-list/{grouping,listing,rows,viewport}`, where
`buildProjectGroupingIndex` produces `WorktreeGroupEntry { label, items: Worktree[], repo?, repoIds:
Set<string> }` — a lane that can span several repo IDs
([`src/renderer/src/components/sidebar/worktree-list/grouping/project-grouping.ts:19`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/renderer/src/components/sidebar/worktree-list/grouping/project-grouping.ts#L19)).
Repos are a first-class plural store (`Repo[]`), organised by nestable `ProjectGroup`s with a
`parentPath` and `parentGroupId`, with nested-repo discovery and import
(`src/main/project-groups/nested-repo-discovery.ts`). 4–5 repos, one sidebar, one window. **PASS.**

#### Deletion policy — from source. **This one beats Claude Code.**

Three independent guards, all fail-closed.

**1. A `git worktree lock` is honoured absolutely, with no force path past it.** The assertion runs
unconditionally at the top of removal, before the `force` branch:

```ts
// src/main/git/worktree-removal.ts:63
  // Why: callers outside the IPC/runtime preflight must not bypass Git's lock contract or rely on localized stderr after side effects.
  assertWorktreeUnlockedForRemoval(removedWorktree)
```

([`src/main/git/worktree-removal.ts:63`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/git/worktree-removal.ts#L63);
also `src/relay/git-handler-worktree-remove.ts:153`, `src/main/local-worktree-removal-recovery.ts:78`
and `:116`, `src/main/ipc/worktrees/removal/remove-registered-local-worktree.ts:80`,
`src/main/ipc/worktrees/removal/execute-worktree-removal.ts:81` — six entry points, all guarded)

```ts
// src/shared/worktree/removal.ts:58
export function assertWorktreeUnlockedForRemoval(
  worktree: Pick<GitWorktreeInfo, 'locked' | 'lockReason'> | undefined
): void {
  if (worktree?.locked) {
    throw createLockedWorktreeRemovalError(worktree.lockReason)
  }
}
```

and — the decisive line — the force-delete classifier **refuses to offer a force affordance for a
locked worktree at all**:

```ts
// src/shared/worktree/removal.ts:93
  if (isLockedWorktreeRemovalError(error)) {
    // Why: a Git lock can represent an external safety contract. It must be
    // unlocked explicitly rather than folded into Orca's dirty-file force path.
    return null
  }
```

([`src/shared/worktree/removal.ts:58`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/shared/worktree/removal.ts#L58),
[`:93`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/shared/worktree/removal.ts#L93))

The user is told to run `git worktree unlock <path>` themselves. There is no button. **Claude Code's
lock is treated as an external safety contract by name.**

**2. Orca sets its own lock, with the owning PID in the reason.** During worktree creation it locks
the in-flight preparation (`'worktree', 'lock', …, lockReason` at
[`src/main/git/worktree-create-preparation.ts:100`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/git/worktree-create-preparation.ts#L100))
and unlocks on completion (`:48`, `:143`, `:262`). Its reclaim sweep for leaked preparations then
reads the PID back out of the lock reason and **only discards one whose owner process is dead**:

```ts
// src/main/worktree-create-preparation.ts:158
        const lockOwnerPid = parseWorktreePreparationOwnerPid(worktree.lockReason)
        const pathOwnerPid = parseWorktreePreparationPathOwnerPid(worktree.path)
        if (!lockOwnerPid || isProcessAlive(lockOwnerPid)) {
          continue
        }
        // Preserve a branch-attached final path after a crash; only detached or
        // still-hidden preparations are safe to discard automatically.
```

([`src/main/worktree-create-preparation.ts:158`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/worktree-create-preparation.ts#L158))

Lock plus PID liveness, and it fails closed when the PID cannot be parsed.

**3. A three-valued PTY-liveness gate that `force` does not waive.** Before a worktree is removed,
Orca stops every PTY scoped to it and then *proves* they stopped:

```ts
// src/main/runtime/unstopped-pty-verification.ts:30
  const livePtyIds = new Set(sessions.map((session) => session.id))
  const stillLive = failedPtyIds.filter((ptyId) => livePtyIds.has(ptyId))
  return stillLive.length > 0 ? { status: 'live', ptyIds: stillLive } : { status: 'exited' }
```

with the third verdict spelled out — *"a stop that lost contact with the PTY's own host stays
**unverifiable**: the surviving provider's inventory is silent about a host it cannot reach, and
silence is not evidence of an exit"*
([`src/main/runtime/unstopped-pty-verification.ts:61`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/runtime/unstopped-pty-verification.ts#L61)).
A `listProcesses` timeout is `unverifiable`, not `exited`, and verification is given a budget of its
own rather than the sweep's leftovers so a slow answer cannot read as a dead process.

And the waiver is separated from the ordinary force:

```ts
// src/shared/worktree/removal.ts:98
  // Why (#11960): this must be decided before the `force` guard below. The ordinary
  // delete confirmation already passes force:true to skip the dirty-file prompt, but
  // it does NOT waive PTY-stop proof — so `force` alone is no evidence that the user
  // has already spent this escape hatch. Only the waiver itself is.
  if (isUnstoppedPtyRemovalError(error)) {
    return allowUnverifiedPtyStop ? null : 'unstopped-pty'
  }
```

The removal-path cache key even encodes it: `const ptyKey = args.allowUnverifiedPtyStop === true ?
'allow-unverified-pty' : 'require-pty-stop'`
([`src/main/ipc/worktrees/removal/worktree-removal-coordinator.ts:17`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/main/ipc/worktrees/removal/worktree-removal-coordinator.ts#L17)).

**One thing to watch, not a hole.** The fast path renames the checkout into a sibling trash
directory and deletes it asynchronously
(`tryRemoveWorktreeWithDeferredDirectoryDeletion`, `worktree-removal.ts:108`). A rename is a
filesystem operation that a git lock would not stop — but it is unreachable while the worktree is
locked, because `assertWorktreeUnlockedForRemoval` has already thrown 45 lines above it, and when
`force` is false it re-proves cleanliness first (*"`git worktree remove` re-checks cleanliness as it
removes; prove the same thing here or leave removal to Git"*), restores the directory from trash if
deregistration fails, and refuses the rename entirely for WSL-owned checkouts. Correct as written;
the ordering is what makes it correct, so it is the thing an upstream refactor could break.

**Does it force? Does it set a lock? Does it check for an attached agent?**
It forces only where git's dirty gate is the obstacle, never where a lock is; **yes, it sets a
`git worktree lock`** with an owner PID during creation; **yes, it checks for an attached agent**,
by proving every scoped PTY exited and failing closed on "could not verify". Two of those three are
things Claude Code does. The third — PTY-liveness independent of the lock — is one Claude Code does
not, and it covers precisely the case a lock does not: **an agent that is alive but whose lock has
been released.** That is the gap #488 identified in `land` and named as worth stealing from Gas
Town; Orca has it, plus the lock Gas Town lacks.

#### The rest

- **Workspace at launch: PASS.** The worktree is created and locked by
  `worktree-create-preparation` before any terminal exists; the agent arrives as a *"Startup command
  threaded onto a worktree's first terminal at activation"*
  ([`src/renderer/src/lib/worktree-startup-payload.ts:13`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/renderer/src/lib/worktree-startup-payload.ts#L13)).
- **Batch review: PASS.** PR pages with CI/checks tabs, and diff annotation that ships comments back
  to the agent (`src/renderer/src/components/pull-request-page/`). No mandatory per-ticket
  interactive gate.
- **Tickets authored elsewhere: PASS, first-class.** *"Browse PRs, issues, and project boards in-app
  — open a worktree from any task"*, with GitHub **and** Linear, Jira, GitLab, Gitea, Bitbucket and
  Azure DevOps modules under `src/main/`. A GitHub issue is bound to a workspace by
  `findGithubIssueWorkspaceAttachment(allWorktrees, repoId, workItem.number)`
  ([`src/renderer/src/components/github-item-dialog/open-dialog/github-item-dialog.tsx:41`](https://github.com/stablyai/orca/blob/5aa02ead59a4f34a186c3e8814558b5795260ee9/src/renderer/src/components/github-item-dialog/open-dialog/github-item-dialog.tsx#L41)).
- **Direct to `main` with no PR: PASS, with a caveat marked "not documented".** Orca does not own the
  merge; a worktree is a real checkout with a real terminal, so `land` runs unchanged. A grep of
  `README.md` for *merge into*, *push to main*, *no PR* and *without a pull request* returns nothing
  — i.e. there is **no documented statement either way**, and nothing in the product forces a PR the
  way Gas Town's Bors queue does. What was checked: `README.md` in full, `docs/` index,
  `src/main/git/*.ts` names. **Not documented** as an affirmative feature.
- **Maintenance signal: the healthiest project in any of these rounds.** 58,917 stars, MIT, not
  archived. Default-branch HEAD **2026-09-01**; releases are *multiple per day* (`v1.4.194` on
  2026-09-01, `v1.4.193` on 2026-08-31, plus a separate mobile release train). Contributors are
  broadly distributed (3,491 / 1,808 / 1,502 / 1,054 human, plus bots). Windows code signing is
  sponsored by SignPath. 5,026 open issues is the one number that reads as strain rather than health.
- **Scale caveat, recorded honestly:** the product surface is enormous — 26+ agent integrations,
  seven forge providers, SSH worktrees, a mobile companion, an embedded browser with Design Mode,
  Computer Use, a VS Code-derived editor, an emulator, a relay, a daemon (`orcad`), and its own CLI.
  Adopting it is adopting an IDE, not a viewer.

---

### forge (kenn-forge)

<https://github.com/kenn-io/forge> — Go + TypeScript, 173 stars.

#### Platform and agent: both fine

Releases for Linux (amd64/arm64), macOS and Windows; one binary serving its UI. It runs external
coding agents in tmux (or a PTY owner) rather than shipping one.

#### Requirement (d) — **PASS**

> Triage activity across repositories and provider hosts.

Confirmed from source rather than the tagline: everything lives in one local SQLite database and
the workspace listing has **no repository filter** — `m.db.ListWorkspaces(ctx)` at
[`internal/workspace/manager.go:4099`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L4099)
and `:4219`, with per-repo lookups (`GetMergeRequestByRepoIDAndNumber`) being the *narrowing*
operations. It also federates: *"View and operate remote kenn-forge daemons through a federated
fleet"*, and the pinned HEAD commit is *"feat: connect Forge fleets through hub-and-spoke f…"*.

#### Deletion policy — from source. **This is where forge loses.**

**Six hardcoded `--force` worktree removals, no `git worktree lock` anywhere, and the agent's
session is killed as step one.**

```go
// internal/workspace/manager.go:3218
	switch state {
	case workspaceCleanupOwned:
		if err := runGitWithoutHooks(
			ctx, gitDir,
			"worktree", "remove", "--force", ws.WorktreePath,
		); err != nil && !isGitWorktreeAbsent(err) {
```

and identically at
[`:2794`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L2794),
[`:2833`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L2833),
[`:3296`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L3296),
[`:5507`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L5507),
[`:5838`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L5838).

A grep of `internal/` for `"worktree", "lock"` returns **nothing**; the only `Locked` identifiers in
the tree are a GitHub PR field, a mutex-held-helper naming convention (`rollLocked`,
`optionalLimitLocked`) and an auth-token helper. forge sets no git lock and reads none.

**The teardown kills the agent first, by design.** `cleanupWorkspaceArtifactsForRetry` opens with:

```go
// internal/workspace/manager.go:3182
	if err := m.cleanupTmuxSession(ctx, ws); err != nil {
		return err
	}
```

and `cleanupTmuxSession` calls `m.ptyOwner.Stop(ctx, ws.TmuxSession)` or kills the tmux sessions
directly
([`internal/workspace/manager.go:3863`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L3863)).
There is no probe of whether the agent is mid-turn, no confirmation that the stop succeeded before
the removal proceeds, and no equivalent of Orca's "unverifiable is not exited".

**What forge does have, and it is worth naming:** a *workspace ownership marker*. Removals verify
that the worktree's registration metadata belongs to this workspace before touching it —
`workspaceRegistrationMatches(ctx, cloneDir, ws.WorktreePath, ws.ID)`, and on a mismatch it
**preserves** the worktree and logs *"rollback: preserved worktree without matching ownership
marker"* (`manager.go:5826`); the failed-creation path returns
`ErrWorkspaceOwnershipUnproven` rather than removing (`manager.go:2782`). Removals are also
serialised under a per-repo lock (`m.withRepoLockForGitDir`). That protects *someone else's*
worktree from forge. It does nothing for *your live agent's own* worktree, which forge kills and
then force-removes.

**Verdict: loses the deciding line**, in the same class as dmux and OpenKanban from #488 — worse
than dmux in that it kills the agent deliberately, better in that its ownership markers mean it
never deletes a worktree it does not own.

#### The rest (recorded briefly, since it is already out)

- **Workspace at launch: PASS.** `runGitWorktreeAdd` builds the checkout, then the session is
  attached; a failure during `configureBareLinkedWorktree` rolls the worktree back
  ([`internal/workspace/manager.go:5496`](https://github.com/kenn-io/forge/blob/b2b8a59a2bbd0555ad699f4bd53524a330b8eb81/internal/workspace/manager.go#L5496)).
- **Tickets authored elsewhere: PASS.** It is a maintainer console — GitHub, GitLab, Forgejo and
  Gitea issues and PRs sync into SQLite, and *"turn any item into a worktree session running your
  coding agent"* is the product.
- **Batch review: PASS.** Reviewing PRs in a sitting is the entire premise.
- **Direct to `main` with no PR: not documented.** Checked `README.md`, `PRODUCT.md`,
  `config.example.toml` and `docs/index.md` — forge is a review console; it does not merge for you,
  so nothing forbids `land`, but nothing states it either.
- **Maintenance signal: young.** 173 stars, not archived, 20 open issues. Default-branch HEAD
  **2026-08-31**; releases **v0.1.0 (2026-08-04)** and **v0.2.0 (2026-08-11)** — still pre-1.0 and
  under a month old. Three human contributors (562 / 257 / 86).

---

## Scoring table

| Line | Claude Code (incumbent) | cc-haha | Agent Orchestrator | Orca | forge | worktrunk | 1code | supacode | nca |
|---|---|---|---|---|---|---|---|---|---|
| Alive | PASS | PASS (HEAD 08-23) | PASS (HEAD 09-01) | PASS (HEAD 09-01) | PASS (HEAD 08-31) | PASS | **FAIL — archived** | PASS | Marginal (HEAD 07-12) |
| Linux / WSL2 | PASS | PASS | PASS (WSL **not documented**) | **PASS + first-class WSL** | PASS | PASS | — | **FAIL — macOS only** | PASS |
| Runs Claude Code | PASS | Fork of it — skills/hooks survive, version does not | PASS | PASS | PASS | PASS (agent-agnostic) | — | — | **FAIL — own agent** |
| 1. 4–5 repos in one view | PASS | **PASS** — sidebar lists all sessions, grouped by project; no filter passed anywhere | **PASS on switching** — global project/session sidebar; the *board* is per-project. Plus one session can span nested repos | **PASS** — `getIndexedAllWorktrees` across every repo, project lanes | **PASS** — `ListWorkspaces` unfiltered, plus fleet federation | **FAIL** — `wt list` is one `Repository` | — | — | — |
| 2. Workspace at launch | **FAIL** — taken on first write | PASS | PASS | PASS | PASS | PASS | — | — | — |
| 3. Batch review | PASS | PASS | PASS | PASS | PASS | n/a | — | — | — |
| 4. Tickets from elsewhere | PASS (`gh` today) | Partial — no issue UI; the agent's shell still runs `gh` | **PASS** — GitHub/GitLab tracker port, spawn by `IssueID` | **PASS** — GitHub + Linear + 5 more, issue→worktree | PASS | n/a | — | — | — |
| 5. Direct to `main`, no PR | PASS (`land`) | PASS | PASS mechanically; card never leaves *Building* | PASS (not documented either way) | Not documented | n/a | — | — | — |
| **6. Deletion — liveness-aware?** | **PASS** — `worktree lock` held for the run; sweep and remove honour it | **FAIL (weak)** — 4× single `--force`, no lock, no liveness; sweep is 30-day + clean + fully-pushed fail-closed | **PASS with one hole** — sweep only on terminated sessions, refuses on open terminal, `Destroy` omits `--force` and names the lock refusal; but `ForceDestroy`'s unconditional `os.RemoveAll` walks past a lock | **PASS — stronger than the incumbent.** Lock honoured with *no* force path; sets its own PID-bearing lock; three-valued PTY-liveness gate that `force` cannot waive | **FAIL** — 6× hardcoded `--force`, no lock, kills the tmux session first | (out on 1, but best hygiene: honours lock as a hard error, never unlocks, ownership check outside the force branch) | — | — | — |
| Maintenance | Anthropic, current | 1,746 commits by one person vs 19 for the next | Daily releases, 6+ contributors, no bus factor | Multiple releases/day, 4 major contributors, 5,026 open issues | v0.2.0, 3 contributors, <1 month old | Very active | Archived | Active but macOS | 1 contributor, no licence |

---

## Bottom line

**Does any of these eight beat staying on Claude Code? Yes — Orca does, and it is the first
candidate in four rounds that wins the deciding line rather than merely surviving it.**

### Where Orca wins, precisely

1. **The workspace at launch.** The worktree is created *and locked* before any terminal exists.
   That is Claude Code's one documented defect, closed.
2. **The deletion policy — and this is the finding that matters.** Claude Code holds a
   `git worktree lock` and honours it. Orca holds a `git worktree lock` **with the owning PID in the
   lock reason**, honours *any* lock as an unwaivable external contract with no force button
   anywhere in the UI, *and* adds a second, independent gate: every PTY scoped to the worktree must
   be **proven exited**, where "could not verify" is a refusal, not a pass, and where the ordinary
   `force: true` confirmation explicitly does **not** waive it. That second gate covers the exact
   case a lock does not — an agent alive after its lock was released — which is the `t294` failure
   that opened this map and the gap #488 flagged in `land`.
3. **Requirement 1 outright**, not on the switching clause: one sidebar, every repo's worktrees,
   grouped into project lanes.
4. **WSL.** It is the only tool in any of these rounds whose source knows that a checkout can live
   inside a WSL distro and that a Windows host must not rename it.
5. **Ticket ingest and maintenance** are both better than the incumbent's status quo: GitHub issues
   are first-class rather than something the agent shells out for, and the project ships multiple
   releases a day across four major contributors.

### What it costs

1. **It is an IDE, not a viewer.** VS Code-derived editor, embedded browser with Design Mode,
   Computer Use, an emulator, SSH worktrees, a mobile companion, a daemon, a relay, 26 agent
   integrations, seven forge providers. Against a workflow whose current defect is "the worktree is
   taken slightly late" — a defect [#478](https://github.com/caneff/agent-skills/issues/478) already
   has a workaround for — this is an enormous amount of machine.
2. **It writes to `~/.claude/settings.json`.** Managed hooks for `SessionStart`,
   `UserPromptSubmit`, `Stop`, `StopFailure` and teammate lifecycle. The merge is additive and
   marker-tagged, and it installs no `PreToolUse` hook, so `rtk`, require-worktree and
   block-dangerous-git are untouched — but a second writer on that file is a new class of risk.
3. **5,026 open issues.** Shipping several times a day at that scale means the thing under you moves
   every day.
4. **`land` surviving is inference, not documentation.** Orca does not own the merge and every
   worktree is a real checkout with a real terminal, so `land` runs — but no primary source states
   the PR-less flow is supported. Recorded as **not documented**, not as a pass.

**Agent Orchestrator is the credible runner-up and is stronger than Orca on two lines Orca does not
touch:** it has no bus factor (six contributors with a real commit distribution — the only candidate
in this survey series where the top contributor is not 5–90× the next), and **one session can hold a
worktree in each of several nested repos**, which is closer to the actual requirement than "several
repos listed in one sidebar". Its deletion policy is the second-best found anywhere: the automated
sweep touches only terminated sessions, refuses when a scoped shell terminal cannot be confirmed
closed, deliberately omits `--force` so a dirty worktree *must* fail, names the lock refusal
explicitly, and preserves every uncommitted byte to `refs/ao/preserved/<session-id>` before any force
path runs. It loses to Orca on three things: no lock is ever set, `ForceDestroy`'s unconditional
`os.RemoveAll` backstop walks straight past a lock the single `--force` could not defeat, and its
Kanban is per-project so requirement 1 passes only on the switching clause. Its own cost is that a
PR-less session never leaves the *Building* column — the operational view it sells is the part that
stops working under `land`.

**cc-haha and forge are rejected.** cc-haha clears requirement 1 handsomely and has the mildest
deletion failure yet recorded — four single-`--force` sites, no lock, no liveness, but a 30-day
fail-closed sweep that never touches unpushed or dirty work — and it is still a *fork of Claude Code
maintained by one person*, which is a larger risk than the workspace-timing defect it fixes. forge
loses the deciding line outright: six hardcoded `--force` removals, no lock read or written, and the
agent's session killed as step one of teardown.

**Four died cheaply and correctly:** 1code is archived, supacode is macOS-only from its own build
targets, `nca` ships its own model loop, and worktrunk — the best-engineered tool here — shows one
repository at a time.

### Recommendation

**Stay on Claude Code for now, but Orca is the first candidate worth an actual trial**, and the
question it should be trialled against is not "is it better" — on the deciding line it demonstrably
is — but "is closing the workspace-at-launch gap and gaining a cross-repo sidebar worth adopting a
daily-moving IDE that co-writes `~/.claude/settings.json`". #485's and #486's conclusion is now
*narrower* than it was: it survives on cost, not on capability.

### The thing worth stealing regardless of the decision

#488 recommended copying Gas Town's `assessStaleness` liveness probe into our own sweep. **Orca
shows the stronger form of the same idea, and it is the one to copy:**

- treat a `git worktree lock` as an **external safety contract** — never unlock, never `--force
  --force`, and never render a force button for a locked worktree, because "the message tells the
  user to force-delete while the UI hides the button is the same dead end"
  (`removal.ts:9`);
- put the **owner PID inside the lock reason** so a reclaim sweep can distinguish a crashed owner
  from a live one without a side-channel;
- make liveness **three-valued** — live / exited / *unverifiable* — and treat unverifiable as a
  refusal, giving the verification its own time budget so a slow answer never reads as a dead
  process;
- keep the **force flag and the liveness waiver separate**, because a user skipping a dirty-file
  prompt has not consented to killing a running agent.

That last point is a direct critique of our own `land`, which has one force concept covering both.

---

## Could not determine

Recorded as gaps, not guesses.

- **Agent Orchestrator — WSL2 support.** Whether the Windows build can drive repositories inside a
  WSL2 distro, or whether the Linux AppImage is expected to run under WSLg. Checked: the README
  install table, `docs/architecture.md`, `docs/development.md`, `docs/daemon-environment.md`, and a
  grep of `backend/`, `frontend/src/` and `docs/` for `wsl` — no hits at all.
- **Orca — whether landing straight onto `main` with no PR is a supported flow.** Nothing forbids it
  and the worktree is a real checkout with a real terminal, but no primary source states it either
  way. Checked: `README.md` in full, the `docs/` tree index, and `src/main/git/` for merge/push
  helpers.
- **Orca — whether its managed hooks in `~/.claude/settings.json` can conflict with a user's own
  `Stop` or `SessionStart` hooks.** The installer uses marker-tagged commands and
  `removeManagedCommands`, and it is explicit about not overwriting the single-slot `statusLine` —
  but no doc or test covers coexistence with a pre-existing user hook on the same event. Checked:
  `src/main/claude/hook-settings.ts`, `src/main/claude/hook-service.ts`,
  `src/main/agent-hooks/installer-utils.ts`.
- **cc-haha — which Claude Code version its `src/` was forked from.** `package.json` says
  `"version": "999.0.0-local"`; there is no upstream version marker, changelog, or `CHANGELOG.md`
  in the tree. Checked: `package.json`, `AGENTS.md`, `README.md`, `release-notes/`,
  `THIRD_PARTY_LICENSES.md`.
- **forge — whether workspace teardown is ever automatic.** All six `--force` removals reached are
  on named user or error-recovery paths (`cleanupWorkspaceArtifactsForRetry`, rollback, failed
  creation). Whether the daemon runs a periodic reaper was not established. Checked:
  `internal/workspace/manager.go` for scheduler/ticker patterns, `config.example.toml`,
  `docs/index.md`.
- **1code — a sunset notice.** The repo is archived, which settles it, but no explicit
  "this project is discontinued" statement exists in the README or the latest release notes.
  Checked: `README.md` in full, the three most recent releases via the API.
