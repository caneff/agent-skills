# Front end after Orca: candidates scored, Claude pass

Date: 2026-09-12. Resolves research ticket
[#706](https://github.com/caneff/agent-skills/issues/706) on wayfinder map
[#700](https://github.com/caneff/agent-skills/issues/700), against the brief at
`docs/research/2026-09-12-front-end-requirements.md`.

Two phases, not merged. Every scored fact comes from the tool's own source, its
own docs, or a local check on this machine. Prior rounds
([#485](https://github.com/caneff/agent-skills/issues/485),
[#486](https://github.com/caneff/agent-skills/issues/486),
[#488](https://github.com/caneff/agent-skills/issues/488)) were used as a
starting name list only; every fact carried forward is re-verified below and
says so.

## Bottom line

**Take Pane (`dcouple/Pane` 2.4.103).** It is the only candidate that is a
Windows-native app with a real WSL2 integration layer, shows every repo in one
sidebar with live per-session agent status, exposes every action `/implement`
needs through a documented CLI contract, and writes nothing to
`~/.claude/settings.json`. It beats Orca on four named lines and loses to it on
one.

Runner-up: **herdr 0.9.0** — better engineered, WSL2-aware in source, the
strongest scripting surface in the field, and it loses on liveness truthfulness
and on having no diff or file surface at all.

Third: **the Claude Code VS Code extension 2.1.269**, which is already
installed here and has a real sessions rail, with one unverified line that
decides it.

---

## Phase 1 — the names

**385 distinct names** swept before any scoring. Sources: six GitHub
search-API enumerations (`search/repositories`, sorted by `updated`, 25-30 per
page) across the phrasings *claude code orchestrator worktree*, *claude code
multi agent manager*, *agent worktree tui*, *coding agent orchestrator
desktop*, *claude code gui*, *multi-repo coding agent dashboard*, *claude code
wsl windows manager*, *kanban claude code codex worktree*, *claude code codex
session manager windows*, and *git worktree multiple repositories agent
sidebar* (171 distinct repos); the curated index
`andyrewlee/awesome-agent-orchestrators` (214 entries, harvested for names
only); `bradAGI/awesome-cli-coding-agents`; the official product pages for the
Claude desktop app and the VS Code extension; and the names carried in from
#485, #486 and #488.

Names are listed by the brief's five candidate classes. The full machine-read
lists are reproducible from the queries above; this section names every
candidate that got as far as a platform or scope check, plus the classes the
rest fell into.

### Class 1 — editors with agent panels

VS Code + `anthropic.claude-code` (2.1.269, installed here) · Cursor · Zed ·
JetBrains (incl. `Swttch` GUI plugin) · Windsurf · `superset` · `wuu` ·
`The-LazyIDE` · `flavor-code` · `distill-code` · `ACUTE-CODE` · `zaivern-code`
· `MendCode` · `XAICode` · `OxideClaw`.

### Class 2 — orchestrator desktop apps

**Orca** (baseline, `stablyai/orca`) · **Pane** (`dcouple/Pane`) · **Agent
Orchestrator** (`Untrivial-ai/agent-orchestrator`) · **Paseo**
(`getpaseo/paseo`) · Nimbalyst · Xum (`coder/mux` → `coder/xum`) · MonoCode ·
Tempest · Berd · Tortie · OpenChamber · Open Session (`tellahq/opensession`) ·
octomux · supacode · Traycer · Proliferate · vibe-tree · Waku · alas · aizen ·
Alethe · Aperant · ateam · automaker · bb · Better Agent · Claude Command
Center · clave · muxel · omg.dev · Ouijit · parallel-code · qm · synara ·
t3code · tlbx · vibecraft · agent-squid · AGX · ai-maestro · AI4Kanban · aizen
· Aeroric · Astera · daintree · agetor · limboo · padu · polaris · maestrus ·
sessio · usine · hive (`unfence-labs`) · Apex · topics-app · dev-3.0 ·
hivemind · mission-control · demeteo · Orbit · crow · groundcrew · ensemblr ·
yolium-desktop · zenban · talos · agentforge · sillage · ai-agent-board ·
CiCy · AgentMux · BearCode · vigil · ClaudeGUI · desktop-cc-gui · pewpew ·
myrlin-workbook · hang4r · omnivue · Kobo · agentrium · crow-central-agency ·
ittop · magent · velpos · arcode · kata-code · Agent-relay · Vellum ·
AutoCoder · quill · MultiAgents-Manager · pannel_handle · ccsm ·
ai-session-manager-portable · Claude-PTY · aki-dev-sync · agentmon · casm ·
MultiClaude · co-pine/multi-agent-manager · flow-state · pragma · baron ·
sequant · dispatcher · claudio · grove (`JollyGrin`) · orka · gg ·
nokto-agent-orchestrator · claude-codex-bridge · claude-team · wiff ·
vscode-workgrid · power-claude · claude-pipeline-manager · workgrid ·
spec-kitty · carl-vibe-kanban · loopforge · holdco · hermes-flywheel ·
vibe-board · openkanban · Cyclops · thurbox · pappardelle · YYLO ·
tmux-ide · agentbox · agterm · ai-devkit.

### Class 3 — terminal tools

**`claude agents`** (CLI 2.1.269, checked here) · **herdr**
(`herdrdev/herdr`) · Claude Squad (`smtg-ai/claude-squad`) · dmux
(`standardagents/dmux`) · Gas Town (`gastownhall/gastown`) · amux · repomon ·
agent-deck · agent-console · agent-manager (`YoanWai`) · agent-of-empires ·
ccmux · rove · grove (`GarrickZ2`) · gwm-cli · moomux · mux-ai · orchardist ·
showrunner · warden · tenx · jind-ai · termpro · feat · dextui · gummi · huu ·
cmux · agentry · reap · openkanban · uzi · container-use · forge · cc-haha ·
worktrunk · nca · 1code · Crystal (deprecated) · Vibe Kanban (sunsetting) ·
Terragon (dead).

### Class 4 — the Claude desktop app

Claude Desktop, **Code** tab (macOS universal, Windows x64/ARM64, Linux beta
via apt/`.deb`).

### Class 5 — a self-built local page

Reading `~/.claude/sessions/<pid>.json`, `git worktree list` per repo, and the
GitHub issue tracker. No upstream; scored on build and maintenance cost.

---

## Phase 2 — scoring

Hard rejects applied cheapest-first, with the line that killed each reject
named. Only candidates that reached a hard-reject check appear in the table;
the ~340 names not listed were set aside in phase 1 as duplicates of a scored
shape, agent-brings-its-own-agent CLIs from the `awesome-cli-coding-agents`
harvest, or single-purpose tools outside the five classes.

### The killing lines

| Candidate | Pinned at | Killed by | The line |
|---|---|---|---|
| Gas Town | `main` @ 2026-07-23, latest release v1.2.1 (2026-06-06) | HR1 dead | `main` has not moved in 51 days; no release in 98. Re-verified: `repos/gastownhall/gastown/commits/main` returns 2026-07-23T13:03:02Z, `releases/latest` returns v1.2.1. The 2026-09-10 `pushed_at` is branch churn, exactly as #488 found. |
| Crystal | README | HR1 dead | Own README: deprecated February 2026. |
| Vibe Kanban | README | HR1 dead | Own README: "Vibe Kanban is sunsetting". |
| Terragon | repo snapshot | HR1 dead | Service ended 2026-02-09. |
| uzi | last commit 2025-06 | HR1 dead | No commit in 15 months. |
| OpenKanban | `main` @ 2026-06-12, v0.1.x | HR1 dead | Three months quiet, one contributor, still v0.1.x. |
| Tortie | repo description | HR2 cannot run here | "A calm agent multiplexer with familiar IDE features, **for macOS**." |
| octomux | repo description | HR2 | "macOS, MIT." |
| supacode | build targets | HR2 | `destinations: .macOS` on every target (#486, not re-verified). |
| agent-console | README | HR2 | "Currently only tested on macOS." |
| Conductor | product page | HR2 | macOS only (#486, not re-verified). |
| Xum (`coder/mux`) | README | HR3 own agent | "custom agent loop but much of the core UX is inspired by Claude Code." Repo now redirects `coder/mux` → `coder/xum`. |
| Cursor Cloud Agents, Factory Droid, Amp, Charlie | — | HR3 own agent | #486, not re-verified. |
| Paseo | 0.8.0, commit `d1b705a` | HR2 (soft) / scored out | Three `wsl` hits in the whole tree, all in `package-lock.json` and React-Native audio/webview files. No WSL awareness in product code. Runs on Linux, so it is admissible, but it brings no answer to the environment the brief names as preferred. |
| **Claude Desktop, Code tab** | docs @ 2026-09-12 | **HR6 not scriptable** | Feature-comparison table: "Scripting and automation \| [CLI] \| **Not available**". CLI-flag table: "`--print`, `--output-format` \| **Not available. Desktop is interactive only.**" And "Flags not listed have no desktop equivalent because they are designed for scripting or automation." |
| Claude Squad | `main` @ 2026-08-20 | HR6 not scriptable | `main.go` registers exactly four cobra commands — root, `reset`, `debug`, `version` — plus flags `--program`, `--autoyes` and a hidden `--daemon`. There is no non-interactive session-create path, so `/implement` cannot dispatch into it. |
| dmux | `main` @ 2026-08-16, commit re-cloned | HR5 removes a live workspace | `['worktree', 'remove', target.worktreePath, '--force']` hardcoded at `src/services/WorktreeCleanupService.ts:84`; a grep for a worktree lock across `src/` returns nothing. Independently re-verified from a fresh clone; matches #488. Also slowing: 27 days since a commit. |
| repomon | `LaneService::delete` | HR5 | `worktree::remove(&rp, &wp, false)` with no lock and no liveness check (#486, not re-verified). 20 stars, one maintainer. |
| forge | six `--force` sites | HR5 | `cleanupTmuxSession` kills the agent as step one of teardown (#488, not re-verified). |
| cc-haha | `"name": "claude-code-local"`, v`999.0.0-local` | HR3 own agent | A fork of Claude Code, not a front end that runs it. |
| Nimbalyst | 1698 stars, pushed 2026-09-12 | HR4 (partial) | Multi-Project Left Rail exists but is off by default and keeps no merged cross-project list (#486). Clears HR4 on the switching clause only. Not re-verified; carried as a scored-down survivor, not a reject. |
| Agent Orchestrator | 11788 stars, commit `1fbfa8a` | HR2 (soft) | Twenty `wsl` hits in the tree, every one in `package-lock.json`, `*_test.go`, mobile `app.json`, or landing-page analytics tests. Zero in product code. Confirms #488's "WSL2 story is absent" from a fresh clone. Admissible (Linux binary), scored down hard. |

### The survivors, scored

Hard rejects: **1** dead · **2** cannot run here · **3** own agent only · **4**
4-5 repos in one view · **5** removes a live workspace · **6** not scriptable ·
**7** no rail · **8** cannot open a session from the rail.

| | **Orca** (baseline) | **Pane** | **herdr** | **VS Code + claude-code** | **`claude agents`** | **Self-built page** |
|---|---|---|---|---|---|---|
| Pinned | v1.4.200, 2026-09-11 | 2.4.103, commit `df04c76` | 0.9.0, commit `d184b41` | ext 2.1.269, VS Code 1.137.0 | CLI 2.1.269 | n/a |
| HR1 dead | pass — `main` moved today, 3 commits on 2026-09-12 | pass — pushed 2026-09-12 | pass — pushed 2026-09-12, 37,982 stars | pass — same version as the CLI | pass | pass |
| HR2 runs here | pass — WSL-aware in source | **pass, best** — `main/src/utils/wslUtils.ts`, Windows-native Electron | pass — `src/platform/linux.rs:23-66` | pass — running here now | pass — running here now | pass |
| HR3 runs my CLIs | pass — 26 integrations | pass — "If it runs in a terminal, it runs in Pane" | pass — "herdr doesn't wrap or replace them; it owns their terminals" | pass — it *is* Claude Code | pass | pass |
| HR4 4-5 repos, one view | pass — sidebar, project lanes | pass — `Sidebar.tsx:538` maps every project | pass — workspace per repo, sidebar rolls up | **unverified** — see below | pass — checked here: 7 sessions across 5 repos | pass by construction |
| HR5 live-workspace removal | **pass, best** — `assertWorktreeUnlockedForRemoval` at six entry points, three-valued PTY gate, no force button | partial — single `--force` hardcoded, no lock; CLI requires `--yes` | fail on the API path — see below | pass — archive skips sessions "open, running, waiting for input, or unread" | pass — lock held for the run | you build it |
| HR6 scriptable | pass | **pass, strong** — 29-command `runpane` contract | **pass, strongest** — CLI + socket API | pass — dispatch is a shell either way | pass — `--json` | pass |
| HR7 rail + live status | pass | pass | pass | pass — `claude-sessions-sidebar` | pass | you build it |
| HR8 open from rail | pass | pass | pass | pass | pass | you build it |
| Many in one repo, grouped | pass | pass — panes per repo | pass — tabs inside a workspace | pass — `addSessionTabToGroup` | partial — flat list | you build it |
| Workspace at launch | **pass** — created *and locked* before any terminal | pass — "You create a session, Pane creates the worktree" | pass — `WorktreeCreate` API | pass — `createWorktree`, scoped to one cwd | fail — takes the worktree on first write (#478) | you build it |
| Batch review, no gate | pass | pass — diff tab per pane | fail — no diff surface | pass | fail — no diff | you build it |
| Tickets authored elsewhere | pass — GitHub issues first-class | not documented | not documented | pass — `gh` in a terminal | pass | pass |
| Truthful liveness | pass — PTY liveness, three-valued | pass — `AgentStatusDot` from agent state | **fail** — Claude Code state is "screen manifest" | pass — status from the session, incl. "waiting for input" | **pass, best** — the registry itself | pass — the registry itself |
| Writes `~/.claude/settings.json` | penalised — co-writes, marker-tagged, no PreToolUse hook | **clean — zero writes** | penalised — opt-in install writes 7 hook events incl. PreToolUse | n/a — it is Claude Code | n/a | clean |
| File open + diff from rail | pass | pass — diff viewer, file explorer, git tree, browser | **fail** | pass — it is the editor | fail | you build it |
| Notify when waiting | pass | pass — notification settings in DB schema | pass — blocked state drives notifications | pass — OS notification | partial | you build it |
| One window | pass | pass | pass | pass | pass | pass |
| Cost | free, open | free, AGPL-3.0 | free, Apache-2.0 | free | free | free |
| Maintenance Chris carries | high — 5,992 open issues, an IDE plus daemon, relay, emulator | low-medium — Electron app, telemetry present | low — one Rust binary | **lowest — already installed** | lowest | **highest — you own it** |
| Maintenance signal | several commits/day, 4 major contributors | pushed daily, `contrib.rocks` contributor wall | pushed daily, 37,982 stars, Homebrew formula | shipped with the CLI | shipped with the CLI | n/a |
| **Verdict** | baseline | **take it** | runner-up | third, pending one check | keep as the fallback | last resort |

---

## One paragraph per survivor

### Pane 2.4.103 — the recommendation

Pane is an AGPL-3.0 Electron app that installs natively on Windows
(`irm https://runpane.com/install.ps1 | iex`) and carries a real WSL2
integration layer rather than a compatibility note. `main/src/utils/wslUtils.ts`
exports `getWSLHome`, `parseWSLPath`, `isWSLUNCPath`, `linuxToUNCPath`,
`getWSLExecArgs`, `buildWSLENV`, `getWSLShellSpawn`,
`getWSLContextFromProject`, `bumpWSLInotifyLimits` and
`validateWSLAvailable` — a per-project WSL context, `wsl.exe` argument
construction with environment export, UNC path translation both ways, and an
inotify-limit bump for file watching inside the distro. The tree carries 592
`wsl` references and a dedicated engineering brief at
`briefs/wsl-performance-bg-cost.md`. That is the shape the brief names as
preferred, and no other candidate in the field has it. The rail is in source:
`frontend/src/components/Sidebar.tsx:538` renders `projects.map((project) =>
…)` inside a "repositories" section, and `ProjectSessionList.tsx` imports
`groupSessionsByProject`, `flattenSessionsByProjects`, `getPinnedSessions` and
`AgentStatusDot`/`AgentActivityDot` — every saved repo in one sidebar, grouped,
each session carrying a live agent dot. Scriptability is a published contract,
not a side door: `contracts/runpane/contract.json` (schemaVersion 1) defines 29
commands including `repos list`, `repos add`, `panes list`, `panes create
--repo <selector> --name <name> --agent <codex|claude|cursor>`, `panes archive
--pane <id> [--force] [--dry-run] --yes`, `workspace state [--repo <selector>]`
("Read one workspace snapshot of every Pane and CLI panel" — `--repo` is an
optional narrowing filter, so the default is every repo), `watch` ("Wait for
workspace agent and Pane transitions using a daemon-held cursor"), and
`panels input` / `submit` / `wait` / `output` / `screen`. Inside a pane the tabs
are agents, diff viewer, file explorer, git tree, logs and a built-in browser,
which covers the whole Orca surface Chris actually uses. It writes **nothing**
to `~/.claude/settings.json`: a grep of `main/src` for `.claude/settings` or
`settings.json` outside Pane's own config returns zero hits. Two honest costs.
First, worktree removal: `main/src/services/worktreeManager.ts:433` runs
`git worktree remove "<path>" --force` with the flag hardcoded, guarded only by
an in-process mutex (`withLock('worktree-remove-…')`), and neither sets nor
reads a `git worktree lock`; `worktreePoolManager.ts:208` and `:267` do the same
for pool reserves. Per #488's premise correction, a *single* `--force` does not
defeat a lock — `git help worktree` requires it twice — so a worktree that
Claude Code has locked for the duration of its run survives Pane. The CLI also
requires `--yes` and offers `--dry-run`. That makes Pane's policy meaningfully
weaker than Orca's and meaningfully stronger than dmux's or repomon's. Second,
it has telemetry: `analyticsManager.track('git_worktree_cleaned', …)` fires on
removal, and `docs/ANALYTICS_INVARIANTS.md` and
`docs/FEATURE_USAGE_TRACKING_INTEGRATION.md` document an event taxonomy. One
provenance note worth knowing: `docs/CRYSTAL_ARCHITECTURE.md` is Pane's own
architecture document, still carrying the Crystal filename — Pane descends from
the Crystal codebase that was deprecated in February 2026, and is its live
continuation under a different owner, alongside Nimbalyst.

### herdr 0.9.0 — runner-up, and the best-built thing in the field

herdr is one Apache-2.0 Rust binary with 37,982 stars, a Homebrew formula, a
Windows installer and an endpoint-protected-Windows page, pushed daily. It knows
WSL2 exists at the level of source, not marketing: `src/platform/linux.rs:23`
declares `WSL_MARKER_ENV_VARS = &["WSL_DISTRO_NAME", "WSL_INTEROP"]`,
`running_inside_wsl()` reads `/proc/sys/kernel/osrelease`, `/proc/version` and
`/run/WSL`, and the unit test at `linux.rs:846` asserts
`text_indicates_wsl("5.15.167.4-microsoft-standard-WSL2")` — the exact kernel
string shape this machine reports. The `CHANGELOG` carries six WSL-specific
fixes (ConPTY cursor flicker, OSC 4 palette bursts leaking into the shell,
WSLg clipboard, host cell size, Windows Git status re-scanning WSL repos).
Its scripting surface is the strongest of any candidate: a CLI *and* a socket
API, with `WorktreeCreate` and `WorktreeRemove` as first-class methods
(`src/app/api/worktrees/deferred.rs`), an agent view with server-side filter
and sort (`AgentViewSetParams`, `AgentViewFilter` with `All`/`Any`/`Not`
composition), and `agent wait --until <state>` so a script can block until an
agent is genuinely blocked. Its concept model fits: "A workspace is the
top-level project container. Use one workspace per repo… Its sidebar state
rolls up from the agents inside it, so you can see which project needs
attention." Two things cost it the top slot. **Liveness is screen-scraped for
Claude Code specifically.** The integrations doc splits agents into "lifecycle
authority" and "session identity", and Claude Code is in the second group:
"The integration reports native session references for restore. **State still
comes from Herdr's screen manifest detection.**" Pi, OMP, Kimi, OpenCode, Kilo
and MastraCode get hook-driven state; Claude Code does not. That is the exact
failure the brief's truthful-liveness line names. **And buying even the session
identity costs seven hooks.** `herdr integration install claude` writes
`~/.claude/hooks/herdr-agent-state.sh` and registers it on `PostToolUse`,
`PostToolUseFailure`, `SubagentStop`, `SessionStart`, `UserPromptSubmit`,
`PreToolUse` and `Stop` (`src/integration/claude_settings.rs:24-52`). A second
writer putting a `PreToolUse` hook into `~/.claude/settings.json` sits directly
on top of `rtk`, `require-worktree` and `block-dangerous-git` — Orca, for all
its bulk, installs no `PreToolUse` hook. The mitigation is real: the
integration is opt-in per agent, `herdr integration uninstall claude` removes
it, `herdr integration status` reports it, and without it herdr writes nothing
to `~/.claude` at all — you just get screen-manifest status either way, so
there is little reason to install it. Third cost: herdr has no diff or file
surface. Panes are terminals; reviewing a diff means running a diff tool in a
pane. Its own worktree removal is the weakest line: `should_shutdown_workspace_
terminal_runtimes_for_worktree_remove` returns `force || cfg!(windows)`
(`src/app/worktrees.rs:7`), so a forced removal — and on Windows *every*
removal — shuts down the workspace's terminal runtimes and then removes,
killing the agent as a designed step. The dirty-file pre-check is
`#[cfg(windows)]`-only. A grep for a git worktree lock across `src/` returns
nothing, and `run_worktree_remove_command_with_recovery` falls back to
`std::fs::remove_dir_all` when git reports "not a working tree". It passes at
most one `--force`, so a Claude-Code-locked worktree still survives it.

### VS Code + `anthropic.claude-code` 2.1.269 — third, and one check from second

This is already installed at
`/home/caneff/.vscode-server/extensions/anthropic.claude-code-2.1.269-linux-x64`,
so it costs nothing to adopt and nothing to maintain. Read from the shipped
`package.json`, it contributes a genuine sessions rail: a `claude-sessions-sidebar`
activity-bar container holding the `claudeVSCodeSessionsList` webview, gated on
the context key `claude-vscode.sessionsListEnabled` — and `extension.js` sets
that key to `true` unconditionally during activation
(`h$.commands.executeCommand("setContext","claude-vscode.sessionsListEnabled",!0)`),
so the rail is live in this version, not behind a rollout flag. The commands
cover the scored lines directly: `claude-vscode.createWorktree`,
`claude-vscode.addSessionTabToGroup` (session grouping, which is the "several
workers on one spec read as one unit" line), `markSessionUnread`,
`renameSessionTab`, `reopenClosedSession`, `window.open`, `terminal.open`,
`acceptProposedDiff`, `rejectProposedDiff`. The archive policy is
liveness-aware and documented in the setting itself:
`claudeCode.archiveInactiveSessions` defaults to 14 days and states "Sessions
that are open, running, waiting for input, or unread are never archived
automatically" — which clears HR5 on the same principle Orca uses. Dispatch
stays a shell command, so HR6 is free. **The one line that decides it is
unverified:** whether the sessions rail lists sessions across *all* folders of
a multi-root workspace, or only the active folder. `workspaceFolders` appears
22 times in the bundle and `createWorktree` resolves against a single
`this.cwd` (throwing "Not inside a git repository"), which hints at per-folder
scoping, but that is an inference from a minified bundle, not a fact. Settling
it needs the rail opened in the existing `~/src/uberworkspace.code-workspace`
— a two-minute check that needs a GUI, which this pass was told not to open.

### `claude agents` (CLI 2.1.269) — the fallback that already works

Checked on this machine, not read off a page. `claude agents --help` lists
`--json` ("Print active sessions (interactive and background) as a JSON array
and exit (for scripting; does not require a TTY)"), `--cwd <path>` as an
*opt-in* narrowing filter, plus `--add-dir`, `--agent`, `--model`,
`--permission-mode`, `--effort`, `--plugin-dir`, `--mcp-config`,
`--setting-sources` and `--restricted` for dispatched sessions.
`~/.claude/sessions/` currently holds 228 entries. #485's verification that it
shows sessions across five repos in one view still holds, and the default being
all-repos with per-path filtering opt-in is the right way round. It clears every
hard reject. It loses the scored lines that make a front end a front end: no
diff, no file open, no grouping of several workers on one spec, a flat list, and
it still takes its worktree on first write rather than at launch (#478's
pre-made-worktree workaround stands). It is the honest floor — adopt nothing,
lose nothing, gain nothing.

### A self-built local page — priced, not recommended

Everything it needs exists: `~/.claude/sessions/<pid>.json` carries cwd, status
and liveness for all 228 sessions; `git worktree list --porcelain` per repo
gives the worktrees; `gh issue list` gives the tickets. It would clear every
hard reject by construction and get truthful liveness for free, because it
reads the registry rather than a screen. It cannot cheaply have what Pane ships:
a real terminal per agent, a diff viewer, file open, and a browser. The
maintenance line in the brief is the whole argument against it — this is the one
option where every future break is Chris's to fix, and it is being considered
precisely because Orca's cost was too high. Build it only if the trial of Pane
fails.

---

## Ranked recommendation

**1. Pane 2.4.103.** The lines it beats Orca on:

- **Windows-native with a real WSL2 layer.** Orca's WSL awareness is one
  refusal-to-rename guard (`worktree-removal.ts:114`, #488). Pane has a
  dedicated WSL module of sixteen exported functions, per-project WSL contexts,
  and a performance brief. Orca had to be run *inside* WSL under WSLg for the
  trial (#488's setup comment); Pane installs on Windows and reaches in.
- **It writes nothing to `~/.claude/settings.json`.** Orca co-writes that file;
  #488 called a second writer on it "a new class of risk". Pane has zero hits.
- **It is a front end, not an IDE.** Orca brings a VS Code-derived editor, an
  embedded browser, Computer Use, an emulator, a daemon, a relay and 26 agent
  integrations, with 5,992 open issues — the cost #692 removed it for. Pane's
  own framing is "Not an IDE. Not a terminal emulator. Vim for agent
  management," and its per-pane tabs cover diff, files, git and browser without
  the machine.
- **A published CLI contract.** 29 commands in a versioned JSON contract with
  `--json` on every read, `--dry-run` and mandatory `--yes` on the destructive
  one, and a `watch` command with a daemon-held cursor for unattended dispatch.

The one line Orca keeps: **deletion safety.** Orca's
`assertWorktreeUnlockedForRemoval` at six entry points, its three-valued
PTY-liveness gate where "unverifiable" is a refusal, and the absence of any
force button in its UI remain the best policy found across five rounds. Pane
hardcodes `--force` with no lock and no liveness probe. The mitigation is that
one `--force` does not beat a lock, and Claude Code sets one for the whole run,
so the `t294` shape is not reachable through Pane for a locked worktree. If the
trial shows otherwise, that is the line to fail it on.

**2. herdr 0.9.0.** Take it instead if the diff viewer turns out not to matter
and a single Rust binary beats an Electron app. It is better engineered than
anything else here and its socket API is the best automation surface in the
field. It costs truthful liveness for Claude Code specifically, and it has no
file or diff surface at all.

**3. VS Code + `anthropic.claude-code` 2.1.269.** Promote it above both if the
sessions rail spans the multi-root workspace. It is already installed, adds no
maintenance, and is the only candidate where the front end and the agent ship
as one version.

### Next step

**Trial Pane, then herdr.** Both install nothing permanent — Pane runs via
`npx --yes runpane@latest` or `pnpm dlx runpane@latest`, herdr is a single
binary from a GitHub release — and both are under an hour to stand up. This
pass did not run either: the brief's trial allowance is real, but standing up a
Windows-native Electron app and clicking its sidebar needs a GUI session, which
this pass was instructed not to open. So a trial is the next step, and it should
answer four questions in this order: does Pane's sidebar really show all 4-5
repos at once with live status; does `runpane panes create` work against a
worktree at `<repo>/.claude/worktrees/<name>` that the agent made, rather than
one Pane made; does `git worktree remove --force` from Pane refuse a worktree
Claude Code has locked; and does the VS Code sessions rail list sessions from
every folder of `~/src/uberworkspace.code-workspace`. The fourth is the
cheapest and could reorder the whole ranking.

---

## Unverified claims

Recorded as gaps, not folded into the verdicts.

1. **Whether the VS Code sessions rail spans a multi-root workspace.** The
   deciding line for the third-ranked candidate. Inferred per-folder from
   `createWorktree` resolving one `this.cwd` and from 22 `workspaceFolders`
   references in a minified bundle. Needs the GUI.
2. **Pane's sidebar behaviour at runtime.** `Sidebar.tsx:538` maps every
   project, and `workspace state` defaults to every repo, but whether all 4-5
   repos are visible *simultaneously* rather than one expanded at a time is a
   rendering question source cannot settle.
3. **Whether Pane refuses a Claude-Code-locked worktree.** Argued from
   `git help worktree` ("To remove a locked worktree, specify `--force`
   twice") plus Pane passing it once. Not executed.
4. **Pane's ticket ingest.** No GitHub-issue integration found in the README,
   the 24 files under `docs/`, or the CLI contract. `gh` in a Pane terminal
   works, but that is not the tool doing it.
5. **Pane's notification trigger.** `notifications` appears in the settings
   schema (`docs/DATABASE_DOCUMENTATION.md:162`) and `notification_shown` is a
   tracked event, but which agent state raises one is not documented.
6. **herdr's worktree-remove UI path.** The API path has no confirmation and no
   liveness refusal, verified from source. A `confirm_close` setting and
   `confirm_implicit_worktree_group_close` exist for the group-close path
   (`src/app/actions.rs:975`), so the interactive path may confirm. Whether it
   gates disk removal specifically was not traced.
7. **Nimbalyst's rail.** Carried from #486 (Multi-Project Left Rail, off by
   default, no merged cross-project list) and not re-verified at 1698 stars /
   2026-09-12. If Pane and herdr both fail their trials, Nimbalyst is the next
   one to read properly.
8. **Agent Orchestrator's deletion hole.** #488 found `ForceDestroy` discards
   the git error then runs `os.RemoveAll` unconditionally. Not re-verified here;
   the candidate was scored down on WSL absence before reaching it.
9. **Whether `/desktop` changes the Claude desktop app's verdict.** The doc
   says `/desktop` moves a CLI session into Desktop on macOS and x64 Windows.
   That is a per-session interactive hand-off, so it does not restore HR6, but
   it was not tested and it is the only bridge between shell dispatch and that
   sidebar.
10. **Class-2 tail.** Roughly 340 of the 385 swept names were set aside in
    phase 1 without a primary-source read, on the strength of a description
    that placed them in an already-scored shape. Three with explicit
    cross-platform, multi-repo claims are the likeliest misses: **MonoCode**
    (885 stars, "macOS, Linux, and Windows"), **Zaivern Code** (9 stars,
    "Cross-platform Rust desktop cockpit"), and **Open Session**
    (`tellahq/opensession`, 373 stars, self-hosted server with Linear/GitHub
    intake). Named so nobody has to re-find them.
