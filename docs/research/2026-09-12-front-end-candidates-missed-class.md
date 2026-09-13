# Front-end candidates the two passes missed: VS Code agent-worktree extensions and kin

Date: 2026-09-12. Ticket
[#708](https://github.com/caneff/agent-skills/issues/708), wayfinder map
[#700](https://github.com/caneff/agent-skills/issues/700), decision ticket
[#704](https://github.com/caneff/agent-skills/issues/704). Scored against
[the brief](./2026-09-12-front-end-requirements.md) — same environment, same
hard rejects in the same order, same evidence standard. This pass covers only
the class the two earlier passes
([#706](https://github.com/caneff/agent-skills/issues/706),
[#707](https://github.com/caneff/agent-skills/issues/707)) missed: VS Code
extensions that manage agent worktrees, plus the repos the ticket named.
Nothing already scored in #706 or #707 is re-scored here.

Two passes, in one document. The first sweeps the marketplace for the five
queries the ticket lists and scores what comes back. The second, added the same
day, scores the ambiguous "Deck" and "Canopy" families by name, three further
extensions and apps, and the herdr add-on ecosystem; it also verifies four
specific lines in `a9a4k.deck` from source. The combined ranking and the answer
for the decision ticket are at the end, and the second pass changes both.

## Phase 1 — the name list, with source

**VS Code Marketplace, queried directly** (POST
`https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery`,
`Accept: application/json;api-version=7.1-preview.1`, criteria filterType 8 =
`Microsoft.VisualStudio.Code` + filterType 10 = the search text, flags 914,
pageSize 40, all five queries run 2026-09-12). The five queries were
`agent worktrees`, `claude code sessions`, `worktree agents`,
`parallel agents`, `agent orchestrator` — 175 result rows, 132 distinct
extensions.

Thirty extensions were pulled for manifest and README reading (every one the
ticket named, plus every other row whose display name or query position
suggested an agent-session or worktree rail). The manifest of each was read
from its gallery asset
(`assetbyname/Microsoft.VisualStudio.Code.Manifest`) for `extensionKind`,
`engines.vscode`, contributed views and repository URL; the README from
`assetbyname/Microsoft.VisualStudio.Services.Content.Details`. Twenty-three had
a public git repo and were shallow-cloned and read.

Named in the ticket, all scored below: `BradenTerry.agent-worktrees`,
`paql4711.agent-space`, `petar-s-dimov.argus-worktree-agent-sessions`,
`barakolsheviz.agent-forq`, `experlab.100doo`, `anse-dev.goly-worktree`,
`norequest.hallucinate-agents`, `adebimpe-dev.trellis-agent-board`,
`LogKat.git-yggdrasil`, plus the four GitHub repos `supabitapp/supacode`,
`NanmiCoder/cc-haha`, `max-sixty/worktrunk`, `automazeio/ccpm`.

Found by the sweep and not in the ticket: `a9a4k.deck`,
`inthepond.agent-view-for-claude-code`, `zarritas.agent-sessions` (Aterm),
`vana123.vswt`, `mkellerman.herdex`, `subhashkhileri.agntree`,
`shaharsha.claude-tower`, `es6kr.claude-sessions`,
`cbeaulieu-gt.vscode-claude-workspaces`, `Toragonite.claude-code-orchestrator`,
`ShebinMohanK.grove-pilot`, `zhoujinjing.hydra-code`,
`kargnas.vscode-tmux-worktree`, `ChronoVortex07.taskwright`,
`visul.terminal-sessions`, `eric-mountain.agent-terminal-sessions`,
`Acycai.agent-worktree-trace`, `KyleJamesWalker.vscode-cc-agent-manager`,
`Vladstack.claude-control-center`, `kendr.kendr-code-vscode`.

Dropped without a row: the remaining ~100 query hits are single-agent chat
extensions (`Continue.continue`, `Blackboxapp.blackbox`, `openai.chatgpt`,
`kilocode.Kilo-Code`, …), plain worktree explorers with no agent model
(`jackiotyu.git-worktree-manager`, `PhilStainer.git-worktree`,
`AbianS.worktree-easy`, `ven7u-labs.worktree-colors`, …), or unrelated
("Parallels Desktop", "Parallel Stacks", `tsandall.opa`). All fail hard reject
7 on their own description; none was read further.

## Phase 2 — scoring

Hard rejects, cheapest first: **1** dead/sunsetting, **2** cannot run here,
**3** brings only its own agent, **4** cannot show 4-5 repos in one view,
**5** removes a live workspace without confirming, **6** not scriptable,
**7** no rail, **8** cannot open a session to answer a prompt.

Reject 3 is read as the brief writes it — a tool that *forces* its own agent
fails; one that runs Chris's chosen CLI but only knows Claude Code passes the
reject and is marked down on the "Codex CLI next" line instead. Every such
case is called out.

### Rejected

| Candidate | Pinned | Killed by | The line that killed it |
| --- | --- | --- | --- |
| `BradenTerry.agent-worktrees` | 4.6.11, commit `315a3d1` 2026-09-10 | 4 | `src/worktreeData.ts:245` — `findRepo()` loops `workspace.workspaceFolders` but `return`s on the first folder that is a git repo: `if (root) return { cwd: key, repoRoot: root };`. One repo is ever the subject. No multi-root repo list exists and none is planned: `multi-root` appears in the repo only in `docs/debug-sessions.md:45` (about a launch-config member form) and `docs/worktree-search.md:37`. |
| `supabitapp/supacode` | commit `81cba55` 2026-09-05 | 2 | `README.md:73` — "macOS 26.0+", built with `Project.swift` / Xcode 26.3. No Linux or Windows binary. |
| `paql4711.agent-space` | 0.5.0, commit `7f1d0f3` 2026-03-12 | 1 | Last release and last commit both 2026-03-12, six months quiet, single maintainer. Otherwise the closest miss of the rejected set: `src/projects/projectManager.ts` keeps an N-project registry in `globalState` independent of `workspaceFolders`, tmux-backed sessions survive restarts, and built-in presets cover `claude`, `codex`, `copilot`, `opencode`. Worth revisiting if it ships again. |
| `norequest.hallucinate-agents` | 0.1.13, commit 2026-07-03 | 4 | `packages/extension/src/extension.ts:1261` — `const folder = vscode.workspace.workspaceFolders?.[0];`, and `src/home-view.ts:47` gates the whole view on `(workspaceFolders?.length ?? 0) > 0` without iterating. Its own coordination brain owns dispatch. Credit where due: it passes hooks per invocation via `--settings` on the CLI argv (`packages/adapter-claude/test/args.test.ts:134`) and never touches `~/.claude/settings.json`. |
| `adebimpe-dev.trellis-agent-board` | 0.1.2, commit 2026-07-19 | 4 | `src/extension.ts:148` and `src/storage.ts:1077` — `workspaceFolders?.[0]`. Board and worktrees are repo-native under `.agent-board/`, one repo per window. It also edits the repo's `.claude/settings.json` permissions (`src/agentPermissions.ts:97`), with consent and a state-only decline (`src/extension.ts:680`). |
| `LogKat.git-yggdrasil` | 0.2.2, 2026-08-05 | 7 | A worktree explorer with no agent model: `README.md` "Explore and switch git worktrees directly from the VS Code sidebar". No session or status concept. Also first-folder only, `src/extension.ts:18`. |
| `anse-dev.goly-worktree` | 1.1.2, 2026-07-07 | 7 | Same shape — "turns Git worktrees into a focused mission-control view"; "see what is running in each one" is process/dev-server, not agent status. No session registry read. |
| `shaharsha.claude-tower` | 0.2.16, 2026-04-29 | 4 | `src/state/TowerStateManager.ts:639`, `src/extension.ts:133/213/335/369/596`, `src/actions/newSession.ts:9`, `src/views/SessionWebviewProvider.ts:171` — every workspace resolution is `workspaceFolders?.[0]`. Notable for what it gets right elsewhere: it reads `~/.claude` state and layers hook-based status over JSONL heuristics (`src/state/SessionScanner.ts`, `src/util/claudePaths.ts`). |
| `subhashkhileri.agntree` | 1.2.1, 2026-05-17 | 4 | `src/providers/WorkspacesTreeProvider.ts:280` and `src/extension.ts:169` — `workspaceFolders?.[0]`; `src/commands/worktree.ts:311` reads `workspaceFolders?.length` only to warn. Reads `~/.claude/projects` (`src/commands/chat.ts`) but scoped to that one folder. |
| `Toragonite.claude-code-orchestrator` | 1.5.3, 2026-08-20 | 4 | `src/views.ts:205/636/1307`, `src/extension.ts:193/457/891/1016/1032/1092/1104`, `src/assetManager.ts:34` — `workspaceFolders?.[0]` throughout. Installs repo hooks wired through `.claude/settings.json` (`src/assets.ts:378-380`). |
| `zhoujinjing.hydra-code` | 0.3.2026082900, 2026-08-29 | 4 | `packages/extension/src/utils/git.ts:61` returns `workspaceFolders[0].uri.fsPath` after an active-editor special case, and `src/commands/autoAttach.ts:24` takes `workspaceFolders[0]` as *the* repo root. Has a real CLI with Codex capability probes (`packages/cli/src/smoke/cliContractSmoke.ts:187`), so the scriptability is there; the repo scope is not. |
| `kargnas.vscode-tmux-worktree` | 1.2.26, 2026-08-25 | 4 | Same lineage as Hydra; `src/commands/autoAttach.ts:13-14` and the plan of record `.sisyphus/plans/tmux-worktree-vscode-ext.md:418` — `return workspaceFolders[0].uri.fsPath;`. Highest-install worktree+agent extension in the class (764) and still one repo. |
| `ShebinMohanK.grove-pilot` | 0.6.0, 2026-03-19 | 1 | Last update 2026-03-19. Would also have taken the heaviest `~/.claude` penalty in the class: it writes `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` into the user's `~/.claude/settings.json` `env` (`vscode-extension/src/core/agent-orchestrator.ts:667-699`) with no opt-out path in the source. |
| `ChronoVortex07.taskwright` | 1.9.1, 2026-07-18 | 4 | `src/extension.ts:1692-1700` — the folder picker resolves to one `selectedFolder`; the board and its worktree guard hook (`scripts/hooks/worktree-guard.ts`) are per-folder. A backlog board, not a cross-repo rail. |
| `cbeaulieu-gt.vscode-claude-workspaces` | 0.4.0, commit `693d3e3` 2026-09-12 | 8 | The best multi-root intent in the class and the wrong session model: it spawns and owns every session through its own node-pty (`src/launch/managedPty.ts`, `src/sessions/sessionManager.ts:124` `pty = await this.dependencies.ptyFactory.spawn(spec)`), and nothing in `src/` reads `~/.claude/projects` or `~/.claude/sessions`. A worker `/implement` dispatches from a WSL shell gets no row, so no prompt can be answered from the panel. Zero mentions of `worktree` in the README. Its own prior-art note (`docs/research/2026-08-23-multi-root-claude-workspaces-prior-art.md:119-124`) is the best writeup of the multi-root problem found in this sweep and is worth reading whatever is chosen. |
| `es6kr.claude-sessions` | 0.4.12, commit `39f3c7d` 2026-08-30 | 7 | Biggest install base in the class by two orders of magnitude (9,300) and not a rail: "Browse, search, rename, split, and clean up Claude Code sessions" (`README.md`). Zero occurrences of `worktree` in the README; no in-flight status. Its cross-workspace resume analysis (`packages/vscode-extension/src/lib/crossWorkspace.ts:9-16`) records that `anthropic.claude-code` resolves a session only against an exactly-matching open workspace folder — relevant to the VS Code + extension option regardless. |
| `visul.terminal-sessions` | 0.32.0, 2026-09-09 | 7 | A terminal-session manager in the explorer view, not an agent rail. It also edits `~/.claude/settings.json` `env` (`src/mouse-clicks-guard.ts:31-150`), removing keys it dislikes. |
| `eric-mountain.agent-terminal-sessions` | 0.1.18, 2026-08-17 | 7 | Tracks agents in its own terminals via a lock file requiring `workspaceFolders` to include the path (`docs/learnings.md:161`); no cross-repo status view. |
| `Acycai.agent-worktree-trace` | 0.1.32, 2026-02-06 | 1, 7 | No commit since 2026-02-06, and `contributes.views` is empty — seven commands, no rail. |
| `KyleJamesWalker.vscode-cc-agent-manager` | 0.9.0, 2026-09-07 | 7 | `contributes.views` empty, two commands. Manages agent definition files, not sessions. |
| `petar-s-dimov.argus-worktree-agent-sessions` | 0.1.0, 2026-07-26 | 8, evidence | No public source (the listing points at an assets-only `argus-support` repo), so no line can be cited — a fail against the #488 evidence standard on its own. Its README is also explicit that rows are the *provider extensions'* native tabs and that it "observes provider session state when reliable local evidence is available": a CLI session started in a WSL shell is not a native tab. |
| `barakolsheviz.agent-forq` | 1.2.12, 2026-09-09 | 4, evidence | No repository URL in the manifest at all. README: dispatch is owned by its own board — "Move an issue to *todo* and Forq automatically spawns an agent session for it" — against Chris authoring tickets on GitHub from wayfinder, and one repo per window. |
| `experlab.100doo` | 0.4.244, 2026-08-27 | 3, 5, evidence | No repository URL. A master agent owns delegation ("delegate a goal to a master agent"), and worktrees self-release: "a finished task with a clean worktree releases the directory automatically", capped by `agentOrch.maxLiveWorktrees`. Uncommitted changes lock it, but liveness of an agent session is not the gate — squarely reject 5. |
| `kendr.kendr-code-vscode` | 0.11.2, 2026-09-12 | 3, evidence | No repository URL; ships its own chat sidebar and agent. |
| `Vladstack.claude-control-center` | 0.2.0, 2026-09-06 | evidence | Manifest points at `github.com/VladislavBI/claude-code-manager`, which returns "Repository not found" (`git ls-remote`, 2026-09-12). Unverifiable. |
| `NanmiCoder/cc-haha` | v0.6.2, commit `85e7f3a` 2026-09-11 | 3 (Codex axis) | The strongest non-VS-Code find and it fails on the agent Chris needs next. Electron, macOS/Windows/Linux (`docs/en/desktop/`), it shares the CLI's own state rather than reimplementing it — reads `~/.claude/projects/{sanitized_path}/{sessionId}.jsonl` (`src/server/services/sessionService.ts:4`) and registers in the `~/.claude/sessions/` PID registry, with a real WSL branch that deliberately skips stale-file sweeping because "a Windows PID won't be probeable from WSL" (`src/utils/concurrentSessions.ts:193-197`). Sessions are tabs, many side by side, a dot for running, and closing a running tab asks Keep running or Stop and close (`docs/en/desktop/sessions.md`). But it is a Claude Code workbench: no Codex CLI anywhere (the one `codex` doc, `docs/en/internals/computer-use-codex-impl-blueprint.md`, is Computer Use compatibility), and a session is bound to one directory. Scope is also enormous — desktop pet, IM integration, H5 remote access, scheduled tasks, skills market — which is maintenance surface Chris does not control. |
| `max-sixty/worktrunk` | commit `89326f1` 2026-09-12 | 7 | A Rust worktree CLI, no window. Very much alive (PR #4000 merged the day of this pass) and a reasonable thing to *use*, not a front end. |
| `automazeio/ccpm` | commit `7d7e462` 2026-03-18 | 1, 7 | A Claude Code command and skill pack for GitHub-issue-driven project management. No rail, nothing to watch, and no commit since 2026-03-18. |

### Survivors

| Candidate | Pinned | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | `~/.claude` writes | Maintenance signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `a9a4k.deck` | 0.24.0, commit `11cde23` 2026-09-11 | pass | pass | pass | pass | pass | pass (via tmux) | pass | pass | **installs 9 Claude hooks + Codex hooks**, dismissible and removable | 80 installs; release commit dated the day before this pass; 26 ADRs, `CONTEXT.md`, a test per behaviour |
| `zarritas.agent-sessions` (Aterm) | 1.3.0, core commit `2767391` 2026-07-29 | pass | pass | pass | pass | n/a | pass (Rust CLI) | pass | pass | none found | 50 installs; open core (`Aterm-labs/aterm`, public) plus a closed Pro module; single squashed commit per repo; last commit 2026-07-29 |
| `inthepond.agent-view-for-claude-code` | 0.9.2, commit `bf8dd00` 2026-08-31 | pass | pass | pass (Claude only) | pass | n/a | partial | pass | pass | **installs hooks in `~/.claude/settings.json`** for Hold/triage | 78 installs; v0.9.2 self-described as pre-1.0 |
| `vana123.vswt` | 0.4.0, commit `ccbbfe4` 2026-06-02 | borderline | pass | pass (Claude only) | pass | pass | partial | pass | pass | none — reads only | 67 installs; "Pre-alpha" in its own README; last release 2026-06-01 |
| `mkellerman.herdex` | 0.1.0, commit `65262a1` 2026-07-28 | borderline | inherits herdr | inherits herdr | inherits herdr | inherits herdr | inherits herdr | pass | pass | none | 163 installs; one squashed commit, one release, unofficial |

## The survivors, one paragraph each

**`a9a4k.deck` 0.24.0** is the best thing this pass found and the only
candidate in the class that clears all eight rejects with Codex covered. Its
tree is not built from `workspaceFolders` at all: repositories live in a
`deck.repositoryRegistry` memento (`src/repository/repositoryRegistryStore.ts:3`)
and every registered repo's worktrees appear under it, so 4-5 repos in one
view is the design, not a workaround, and worktrees created from a shell are
discovered (`README.md`: "only for Deck-created worktrees, not ones it
discovers from the CLI", describing the launcher exception). Terminals are
tmux sessions on a private server (`tmux -L deck`), opened as editor tabs and
enumerated live from the server with a path-derived prefix —
`wt-${tmuxSafe(worktreePath)}__term-<N>` (`src/terminal/tmuxSafe.ts:9-14`),
where `tmuxSafe` replaces `[:./]` with `_`. That is the scriptability answer:
a shell can create a row by starting a tmux session on the `deck` server under
that name with `DECK_SESSION` set, because rows come from
`tmux list-sessions` (`src/terminal/tmuxCli.ts:127-138`), not from an internal
list. Status is real and covers both agents — nine Claude hook events and five
Codex ones (`src/agent/hookInstaller.ts:7-20`) write JSON to
`~/.local/share/deck/status/`, with notifications on needs-input and
completion, suppressed while you are looking at that tab. Three costs, all
named: it writes those hooks into `~/.claude/settings.json`
(`src/extension.ts:158`, `src/agent/agentDetection.ts:48`) behind a preview
prompt with a "Don't ask again" that persists
(`src/agent/agentSetupPrompt.ts:113-120`) and a `deck.removeAgentHooks`
command, so it is opt-out-able but it is a write; the hook script begins
`if [ -z "${DECK_SESSION:-}" ]; then exit 0; fi`
(`src/agent/agentHookScript.ts:24-26`), so an agent started in a plain WSL
shell produces no status at all until a wrapper puts it in a Deck tmux
session; and a switch is `vscode.openFolder`, where "the new folder becomes
the sole workspace root" (`docs/adr/0003-single-folder-switching-via-openfolder.md`),
which replaces the `uberworkspace.code-workspace` multi-root window with one
folder. Worktree removal is always modally confirmed and refuses the active
and main worktrees (`src/worktree/worktreeRemoval.ts:12-24`,
`src/worktree/worktreeRemovalCommand.ts:78,100`), though the confirmation
warns on uncommitted changes and unpushed commits rather than on a live agent.

**`zarritas.agent-sessions` (Aterm) 1.3.0** is the only survivor that is both
multi-agent and genuinely scriptable, because its brain is a Rust CLI and the
extension is a client of it. Seven providers including Claude Code and Codex,
each read in its native format, so a session started anywhere appears; live
status comes from `runCli(["live"])` (`src/extension.ts:411`), and the core
resolves that from `~/.claude/sessions/<pid>.json` probed with `kill(pid, 0)`
(`crates/agent-sessions/src/live.rs:2,66-67,121`) — exactly the truthful
liveness the brief asks for. It launches new sessions into several projects at
once, each in its own git worktree, and notifies when one finishes or waits.
The marks against it: the live-status path is Claude-only today, stated in its
own roadmap table — `~/.claude/projects/**.jsonl` plus
`~/.claude/sessions/*.json` "vivo" for Claude Code, history only for the rest
(`docs/providers-roadmap.md:18`) — so Codex sessions appear without a live
light; the UI is a session browser first and a repo rail second; the README and
commit messages are Spanish-first with English secondary; each repo is one
squashed commit with no history to read; and there is a closed Pro module whose
absence downgrades commands to an "edición Pro" notice (`src/pro-api.d.ts:1-9`).

**`inthepond.agent-view-for-claude-code` 0.9.2** solves the one thing Deck
needs a wrapper for. Its fleet is built by scanning all of `~/.claude/projects`
with no workspace scoping at all (`src/discovery.ts:50-70`), so every session
`/implement` dispatches from a WSL shell, in any repo, appears in the panel
with live status, a triage view, a board, and notifications;
`workspaceFolders?.[0]` appears only as the default cwd for spawning
(`src/extension.ts:100-106`). Two marks: it is Claude Code only by name and
design, so it carries none of the Codex half of the brief; and its Hold feature
is "implemented by a hook in the user's `~/.claude/settings.json`"
(`src/extension.ts:1122`, installer at `src/hooks/installer.ts`), a penalised
write, though the rest of the panel works without it.

**`vana123.vswt` 0.4.0** is the closest fit to Chris's exact conventions and
the weakest bet on maintenance. It is the one extension in the sweep whose repo
discovery is unambiguously multi-root: `discoverRepos` maps over every
workspace folder, descends to a configurable depth, and dedupes repos by
`git rev-parse --git-common-dir` (`src/extension.ts:99-114`), which is precisely
the ten-folder-workspace case `BradenTerry.agent-worktrees` fails. It reads
Claude's live registry and filters stale pids with `process.kill(pid, 0)`
(`src/sessions/session-scanner.ts:73-101,304-309`), and it already knows the
worktree path Chris is standardising on: worktrees under
`<repo>/.claude/worktrees/` get their own icon
(`src/sessions/sessions-tree-provider.ts:559`, icon at `:396`, README: "Worktrees created by
`claude --worktree` … get a ✦ sparkle icon"). It writes nothing to `~/.claude`.
Against it: its own README says "Pre-alpha", the repo is a single squashed
commit, the last release was 2026-06-01, and the session model is Claude-only.

**`mkellerman.herdex` 0.1.0** matters only as a rider on the option already
ranked first. It is an unofficial VS Code client over herdr's local socket
(`~/.config/herdr/herdr.sock`), documented against a live server in
`docs/research/herdr-socket-api.md`, and it reimplements nothing: herdr owns the
PTYs, agents and detection. The Workspaces view is `Workspace → Tab → Pane` for
every herdr workspace, with an Agents view sorted by attention
(blocked → done → working → unknown → idle) and a badge when one needs you;
VS Code's own folders are used only to scope the Agents view and decide whether
opening needs a new window (`src/vscode/workspaceResolver.ts:1-26`), so the
multi-repo answer is herdr's, not the extension's. Agent kinds include claude
and codex (`src/commands/index.ts:75`). Status polls `session.snapshot` every 2s
because herdr does not push status on global subscriptions (`README.md`), which
is a cost on a busy rail. It is v0.1.0, one squashed commit, one release,
2026-07-28, by a single maintainer — thin, but its failure mode is degraded
views over a herdr that keeps working.

## Second pass: the Deck and Canopy variants, three more, and herdr's add-ons

Added after the first pass, on the same standard. "Deck" and "Canopy" are both
ambiguous names; every variant that is not macOS-only is scored and named
precisely below.

### Extra names, with source

Marketplace manifests and READMEs pulled the same way as the first pass, 2026-09-12:
`nvitlam.agent-deck` 0.7.1, `SingularityInc.canopy` 0.7.6,
`wimmol.vscode-agentic` 0.8.3, `statiolake.vscode-herdr-switcher` 0.2.0,
`xicu.herdr-companion` 0.3.0, `clement-micol.herdr-bridge` 0.1.0,
`endoumame.herdr-vscode` 0.2.3. Every one of those manifests carries a
`repository.url`, so all were cloned and read.

GitHub, shallow-cloned and read: `asheshgoplani/agent-deck`,
`Wintersta7e/agentdeck`, `beaufour/orca`, `canopyide/canopy-orchestrator`,
`itsoltech/canopy-desktop`, `daintreehq/daintree`, `johannesjo/parallel-code`,
`juliensimon/canopy`, `canopy-hq/canopy`, plus the six herdr plugins
(`persiyanov/herdr-reviewr`, `ogulcancelik/herdr-browser`,
`alexarthurs/herdr-sidebar`, `dcolinmorgan/herdr-remote`,
`nikok6/herdr-mirror`, `smarzban/herdr-file-viewer`).

Sites read directly: `canopy.itsol.tech`, `canopyide.com`, `claudedeck.ai`.

Two corrections to the names as given:

- **`canopyide.com` now serves `daintree.org`.** Canopy IDE was renamed
  **Daintree** and lives at `daintreehq/daintree`. The
  `canopyide/canopy` repo its orchestrator README links to returns 404, and
  `canopyide/canopy-orchestrator` has not been pushed since 2026-03-07. The
  live product is scored below under Daintree, and it is the most important
  find of either pass.
- **`web3dev1337/agent-workspace` does not exist.** `git clone` returns
  "Repository not found" and the GitHub API returns nothing for that path as of
  2026-09-12. No substitute was guessed at. Unscored.

### `a9a4k.deck` — the four lines verified

All four were read from source in the clone at commit `11cde23` (v0.24.0).

1. **Hard reject 5 — a live agent does not block or annotate removal, and the
   removal kills it.** `warningDetail()`
   (`src/worktree/worktreeRemovalCommand.ts:205-215`) builds the modal's detail
   from exactly three facts: `uncommitted changes`, `unpushed commits`,
   `locked worktree`. A running agent is not among them. `canRemoveWorktree()`
   refuses only the active worktree and the main worktree
   (`src/worktree/worktreeRemoval.ts:12-24`). Under ADR-0016 the removal is
   then optimistic: the row disappears at once and, detached, it runs
   `terminalCascade.killWorktree(node.worktree.path)` before
   `removeWorktree` (`:150`). **Which way it falls:** it passes the reject as
   literally written, because a modal always confirms, and fails the intent —
   Chris is never told that the thing he is about to delete has a working agent
   in it, and the kill is unconditional.
2. **Hard reject 6 — yes, a shell dispatcher can create a Deck terminal, and
   here is the recipe.** Terminal rows are not read from an internal list; they
   come from the live server, `tmux list-sessions` filtered by a path-derived
   prefix (`src/terminal/tmuxCli.ts:127-138`, called with
   `terminalSessionPrefix(worktreePath)` at `src/extension.ts:1035`). The
   server is `baseArgs() = ['-L', 'deck', '-f', this.configPath]`
   (`src/terminal/tmuxCli.ts:330`), so the socket is the `deck` socket under
   `/tmp/tmux-$(id -u)/`. The name is
   `wt-${tmuxSafe(worktreePath)}__term-<N>`, where `tmuxSafe` replaces each of
   `:`, `.` and `/` with `_` (`src/terminal/tmuxSafe.ts:1-14`), and
   `ensureSession` creates it as `tmux … new-session -d -s <name> -e
   DECK_SESSION=<name> -c <cwd>` (`:70-84`). A dispatcher reproducing that name
   and that `DECK_SESSION` value gets a row with live status. **Which way it
   falls:** passes, at the cost of a wrapper Chris owns that duplicates Deck's
   naming convention — a maintenance line, and one that breaks silently if the
   convention changes.
3. **Hooks are effectively mandatory for status; the probes only repair a known
   session.** Every status value is written by the hook script, and that script
   exits early when the variable is absent:
   `if [ -z "${DECK_SESSION:-}" ]; then exit 0; fi`
   (`src/agent/agentHookScript.ts:24-26`). `AgentLivenessProbe.isAgentAlive`
   takes a pid and start time it is *given* and checks them with
   `process.kill(pid, 0)` plus a `ps -o lstart=` match
   (`src/agent/agentLivenessProbe.ts:17-35`). `AgentPaneProbe.identityForSession`
   does derive an identity with no hook — pane pid, first child, start time
   (`src/agent/agentPaneProbe.ts:13-23`) — but its only caller is
   `adoptLivePaneIdentity`, which requires an existing hook-written sidecar to
   graft onto and exists for the resume case: "The resumed agent fired no hook,
   so the row still carries tmux's automatic-rename"
   (`src/agent/agentExitSweep.ts:161-180`). **Which way it falls:** no hooks,
   no status. The `~/.claude/settings.json` write is the price of the feature,
   not an optional extra, though the prompt is declinable permanently
   (`src/agent/agentSetupPrompt.ts:113-120`) and `deck.removeAgentHooks` undoes
   it.
4. **Hard reject 4 — yes, the tree shows status for every registered repo, not
   only the active folder.** Status is keyed by tmux session name in
   `AgentStatusStore` (`src/agent/agentStatusStore.ts:26-45`), and the
   decoration layer carries a `repositoryPath` per terminal and rolls a
   collapsed repository row up to `nodeKey('repository', terminal.repositoryPath)`
   (`src/agent/agentStatusDecorations.ts:29,166-167`), with decoration kinds
   `'repository' | 'worktree' | 'terminal'`
   (`src/agent/agentStatusDecorationUris.ts:15`). Nothing in that path consults
   `workspaceFolders`. **Which way it falls:** passes cleanly. One active editor
   folder, status for all of them.

### Rejected in the second pass

| Candidate | Pinned | Killed by | The line that killed it |
| --- | --- | --- | --- |
| `Wintersta7e/agentdeck` ("AgentDeck", Electron) | 7.0.0, commit `e8b5fce` 2026-08-26, pushed 2026-09-06 | 6 | **The closest environment match in either pass, lost on scriptability.** "A desktop deck for your WSL coding agents … it spawns `wsl.exe`, so there's no native Linux/macOS build" (`README.md:5,73`) — Windows 11 + WSL2 by design, which is exactly what the brief prefers, with 7 built-in agents including Claude Code and Codex plus custom CLIs, per-session worktree isolation with a Keep/Discard flow, and a live session grid. But `package.json` declares no `bin`, it "ships as a portable `.exe`", and `src/main` contains no protocol handler, no `second-instance`/`process.argv` handling and no listening socket — nothing outside the GUI can start a session. Nothing reads `~/.claude/projects` or `~/.claude/sessions` either, so a shell-dispatched worker is invisible (reject 8 as well). Elastic-2.0, 4 stars, one author, self-described as "shaped around exactly one setup". |
| `nvitlam.agent-deck` ("Agent Deck", VS Code) | 0.7.1, commit `5e37001` 2026-09-11 | 8 | Self-declared: "Agent Deck observes. It never acts." (`README.md:86`). There is no way to answer a prompt from the panel. Otherwise a well-built thing with the cleanest position on the penalised line in the whole sweep — "**Read-only.** It never writes to your agents' settings, your session files, or anything under `~/.claude`" (`README.md:88`); the hooks are a block the user pastes themselves. Covers Claude Code, OpenCode and Codex on one loopback listener, reading `~/.claude/projects`. |
| `itsoltech/canopy-desktop` ("Canopy", IT SOL) | 0.12.0 shipped, repo at 0.13.0-next.30, commit `529bd58` 2026-09-12 | 6 | Free, source-available, Electron, macOS/Windows/Linux, multiple projects, a worktree sidebar with running/idle/waiting, a terminal and Chromium tab per worktree, an Inspector with per-session cost and tokens, and dedicated adapters tracking state for Claude Code, Codex, Gemini CLI and OpenCode (`docs/integrations/agents.md:11`). It loses on dispatch: `package.json` declares no `bin` and there is no CLI or API surface, and status is routed by PTY session id from hook scripts it injects per session into a private config, so only sessions Canopy spawned exist (reject 8 too). **Worth stealing from regardless:** its Claude adapter writes a throwaway settings file and passes `--settings <path>`, unlinking it afterwards (`src/main/agents/adapters/claude.ts:82-97`) — hook-based status with `~/.claude/settings.json` untouched, which is strictly better than Deck's approach. Its own Windows note is a warning for this environment: if `.sh` is associated with Git Bash or WSL bash, "each hook event would open a new visible terminal window" (`docs/integrations/agents.md:13`). |
| `SingularityInc.canopy` ("Canopy — Multi-Repo Worktree Manager") | 0.7.6, commit `9484e83` 2026-05-31 | 7 | Genuinely multi-repo and genuinely scriptable — a VS Code surface over the `canopy-cli` CLI plus MCP server, reading "the same JSON contract the CLI ships — what you see here is what `canopy state` / `canopy triage` / `canopy feature status` would show in a terminal" (`README.md:5`). But the unit is a *feature* across repos with its PRs, review threads and CI, not an agent session: no live agent status anywhere, and agents appear only as an "Address in agent" action on a review thread. Reject 1 is borderline too (2026-05-31), and `Canopy: Mark Feature Done` "archives a feature: removes worktrees, deletes branches" (`:72`) with no live-agent gate. **The best batch-review surface found in either pass**, which is a scored line — worth a look if that line dominates. |
| `canopyide/canopy-orchestrator` | commit `790e0d6` 2026-03-07, 0 stars | 1 | Not the IDE — a "pre-configured workspace" that points an MCP agent at Canopy IDE's MCP server. Six months without a push, and superseded: the IDE it orchestrates is now Daintree. |
| `juliensimon/canopy` | commit `295aca4` 2026-08-23 | 2 | "The cockpit for parallel Claude Code sessions — **a native macOS app**", macOS 14+, `Canopy.dmg` only (`README.md:5,19,25`). |
| `canopy-hq/canopy` | last push 2026-06-12 | 1 | **Archived** (`archived: true` from the GitHub API, 2026-09-12). |
| Deck View, Deck View Selector, Pocket Deck (`claudedeck.ai`) | Deck View 0.18.25, Selector 1.3.5 | 2 | "Native macOS app", every download an `aarch64.dmg` for "macOS Apple Silicon"; Pocket Deck is iPhone. Paid from £7/mo. No KeepDeck product is listed on the site as of 2026-09-12. |
| `beaufour/orca` (the other Orca) | 0.1.0, commit `5aea2ac` 2026-05-02 | 1 | A Tauri desktop app for "parallel Claude Code and Opencode sessions across repos and git worktrees" — the right shape, stopped at v0.1.0 with no commit in over four months. |
| `wimmol.vscode-agentic` ("Agentic") | 0.8.3, commit `a68a28e` 2026-05-16 | 1 | Maintenance checked first as instructed: one squashed commit, one author, nothing since 2026-05-16, 159 installs. It would otherwise have scored respectably — `addRepo`/`removeRepo` manage several repos as workspace folders (`src/features/addRepo.ts:29,108`) and it reads Claude's own transcripts at `~/.claude/projects/<encoded-path>/<sessionId>.jsonl` (`src/services/TerminalService.ts:50`), describing itself as "a convenient wrapper of Claude Code TUI that brings no limitations". |
| `johannesjo/parallel-code` | commit `508c8e5` 2026-09-12, MIT | 6 | Not reject 2: it ships a Linux `.AppImage` and `.deb` alongside the macOS `.dmg` (`README.md:116-117`), and a Linux build is admissible under the brief, so WSLg is not the deciding question — it simply is not the preferred Windows-native shape. It dies on dispatch instead: no `bin`, no API or CLI, no `~/.claude` session reads, and tasks are created in the GUI. Very much alive and otherwise well aimed — Claude Code, Codex CLI, Gemini CLI and Copilot CLI, a worktree per task, "See every session in one place", diff review with inline comments. |
| `web3dev1337/agent-workspace` | — | unverifiable | Repository not found (`git clone`, and the GitHub API, 2026-09-12). |

### New survivors

| Candidate | Pinned | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | `~/.claude` writes | Maintenance signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `daintreehq/daintree` (was Canopy IDE) | 0.36.1, commit `78a46be` 2026-09-12 | pass | **pass, Windows→WSL** | pass | pass | **pass, best in sweep** | pass (MCP) | pass | pass | none to the user's own | 71 stars, 11 contributors, PR #12392 merged the day of this pass; free app, Apache-2.0 per the site |
| `asheshgoplani/agent-deck` (Go TUI + web + CLI) | commit `684dd21` 2026-09-12, MIT | pass | pass (WSL) | pass | pass | pass | **pass, CLI-first** | pass | pass | MCP attach writes `~/.claude/settings.json` | 875 stars, pushed the day of this pass, actively recruiting co-maintainers (issue #1650) |

**`daintreehq/daintree` 0.36.1** is the strongest candidate this ticket found,
and it is the one that can move the decision. It was Canopy IDE;
`canopyide.com` now serves `daintree.org`. It is deliberately not an editor:
"Daintree sits above the agent CLIs you already run, not inside another VS Code
fork", running "the CLI binary you already run, with your config" — 17 built-in
agents with live state detection, Claude Code and Codex CLI named first. The
rail is the product: Pilot "brings every run into one view, grouped by project
and ordered by live agent state … blocked, waiting for approval, or ready to
review", which answers rejects 4, 7 and 8 in one surface rather than three
features. **On environment it does the thing the brief says it prefers**: the
Windows build reaches into WSL on purpose, routing git through `wsl.exe git`
with a targeted distro and translating paths across the 9P mount
(`electron/utils/hardenedGit.ts:57,431-513`, `electron/store.ts:265`), with
`isWslPath`, `wslDistro`, `wslPosixPath`, `wslGitEligible` and an opt-in
`wslGitOptIn` carried per worktree (`src/store/createWorktreeStore.ts:2183-2188`).
**On hard reject 5 it is the most careful implementation in either pass**: the
project-removal handler "fails closed: does NOT remove the project when the
teardown is unconfirmed", because "removing the row would orphan the still-
running agents (#11340)"
(`electron/ipc/handlers/__tests__/project.remove.test.ts:178-186`), and a live
agent holds a deleted worktree's row open for an hour against five minutes for
a mere dialog or drag, reasoned as "force-trashing a live agent is closer to
termination than to a reversible undo"
(`src/store/deletedWorktreeCleanup.ts:18-33`). **On hard reject 6 it has the
best scriptable surface of anything scored**: a local MCP HTTP server that
exposes the whole action system, where "a `tools/call` request resolves to an
`ActionService.dispatch(actionId, args)`"
(`docs/architecture/mcp-server.md`), with `agent.launch`,
`worktree.createWithRecipe`, `worktree.waitUntilReady`, `terminal.sendCommand`,
`terminal.waitUntilIdle`, `fleet.getRunStatus` and the full `forge.*` set —
dispatch that `/implement` can drive directly instead of through a naming
convention. **The "~250 MCP tools" figure carried over from the Canopy IDE
framing is not what the source shows.** The action registry holds 441 ids
(`src/services/actions/definitions/`), of which the MCP server projects a
subset by `mcpVisibility` and authorization tier: the architecture doc names
128 distinct `x.y` tool ids, and the generated manifest served to a
workspace-bound external session with no single live view carries 32
(`electron/services/mcp-server/generated/mcpExternalBaseManifest.ts`, itself
"a projection of production code rather than a second source of truth"). So the
surface is real and large enough to clear hard reject 6 outright, but its size
depends on view binding and tier rather than being one fixed count. It also covers two scored lines nothing else does: GitHub issues in
bulk, where you "pick issues in bulk; each one gets its own worktree and
agent", and a Review Hub that puts every worktree's diff beside its merge
readiness and forge CI with no per-ticket interactive gate. Two real costs.
First, **liveness is the mechanism the brief marks down**: state comes from
`ActivityMonitor` and `PtyEventsBridge` reading PTY output through polling
tiers and hysteresis (`docs/architecture/agent-activity-monitoring.md`), not
from `~/.claude/sessions/<pid>.json` or process state — the doc's own strategy
note argues against the alternatives, but it is still terminal-derived. Second,
its sessions are the ones it spawns, so a worker started in a bare WSL shell
appears only if dispatched through Daintree, and MCP is off by default and must
be enabled and bound to localhost with an authorization tier. It writes
`.claude/settings.json` only inside its own bundled help-assistant session
directory (`electron/services/HelpSessionService.ts:730`), never the user's.

**`asheshgoplani/agent-deck`** is the scriptability answer in its purest form:
the CLI is not an afterthought bolted onto a GUI, it is the product's front
door. `agent-deck add . -c claude --worktree feature/a --new-branch` creates a
session in a new worktree from a shell (`README.md:323`), with
`agent-deck session send <id> --message-file task.md`,
`agent-deck session fork`, and `agent-deck web` serving a UI on
`http://127.0.0.1:8420` beside the TUI. The pitch is Chris's exact case:
"Running Claude Code on ten projects, OpenCode on five more … One terminal
shows every session — running, waiting, or done — and one keystroke switches
between them" (`README.md:22`). Codex is real, not aspirational — forking is
"verified with `codex-cli 0.137.0`" (`:154`) — and it reads Claude's own live
registry, `~/.claude/sessions/<PID>.json`, to reconcile session titles
(`internal/session/claude_title_reconcile.go:12`). It runs sessions in tmux and
can be pinned to its own tmux server by one config line so it never touches an
interactive tmux (`README.md:815-820`), and it explicitly preserves a
dotfiles-managed symlink when it rewrites `~/.claude/settings.json` for MCP
attach (`internal/atomicfile/atomicfile.go:7`) — a write, opt-in and for MCP
rather than status. MIT, 875 stars, pushed the day of this pass, and openly
looking for co-maintainers, which cuts both ways: real momentum, one owner
today. The honest mark against it is shape, not capability: the rail is a TUI
plus a browser tab, not a panel in the window Chris already has open.

## The herdr ecosystem

Herdr itself is not re-scored. For the record it is `herdrdev/herdr`
(**not** `ogulcancelik/herdr`, which 301-redirects), v0.9.0, Apache-2.0,
37,989 stars, pushed 2026-09-12.

**Is any of these first-party? No.** The marketplace at `herdr.dev/plugins` is
an automatic index, not a curated one: it "lists public repositories tagged with
the GitHub topic `herdr-plugin` when their default branch contains at least one
`herdr-plugin.toml`", and "Discovery is automatic and unreviewed. A listing
means a repository tagged itself, not that Herdr vetted it"
(`docs/preview/website/src/content/docs/marketplace.mdx`). Install is
`herdr plugin install owner/repo[/subdir...]`. None of the add-ons below is
named anywhere in herdr's own docs.

| Add-on | Pinned | Source | Last push | Maintainers | Official install path | Gap in the brief it closes |
| --- | --- | --- | --- | --- | --- | --- |
| `persiyanov/herdr-reviewr` | `herdr-plugin.toml` 0.36.2 | GitHub, MIT, 685 stars | 2026-09-05 | 1 | yes, manifest present | **File open and diff from the rail** — the scored line herdr has no answer for |
| `smarzban/herdr-file-viewer` | 1.16.0 | GitHub, MIT, 569 stars | 2026-09-10 | 1 | yes | File open from the rail, the read half of the same gap |
| `dcolinmorgan/herdr-remote` | 0.8.0 | GitHub, no SPDX license, 354 stars | 2026-09-11 | 1 | yes | **Notification when an agent is waiting** — menu bar, phone, Telegram |
| `nikok6/herdr-mirror` | 0.4.3 | GitHub, MIT, 228 stars | 2026-09-06 | 1 | yes | Cross-machine rail: "One window shows the agents on every machine — blocked, working, done" |
| `alexarthurs/herdr-sidebar` | not versioned | GitHub, MIT, 329 stars | 2026-09-12 | 1 | **no manifest** — not installable via `herdr plugin install`, not listed | File explorer plus a source-control panel in a herdr pane |
| `ogulcancelik/herdr-browser` | — | GitHub, MIT, 348 stars | 2026-08-22 | 1 | **no manifest** | **Deprecated — do not consider.** "This project is no longer maintained. Use terminal-browser instead." Would have covered the embedded browser Orca had |
| `mkellerman.herdex` | 0.1.0 | `mkellerman/herdex`, MIT, 2 stars | 2026-07-28 | 1 | VS Code extension, not a herdr plugin | herdr's rail inside VS Code (scored in the first pass) |
| `statiolake.vscode-herdr-switcher` | 0.2.0, 342 installs | `statiolake/vscode-herdr-switcher`, MIT, 2 stars | 2026-08-31 | 1 | VS Code extension | Switch between per-space VS Code windows and jump to an active agent. **Caveat: its manifest declares `extensionKind: ["ui"]`, so it runs on the Windows host, not the WSL extension host** — the wrong side of the boundary for repos living in WSL |
| `xicu.herdr-companion` | 0.3.0, 30 installs | `XicuM/herdr-companion`, MIT, 0 stars | 2026-09-04 | 1 | VS Code extension | Conversation management across opencode, claude, codex and more, with an agent status map. Contributes **no views** |
| `clement-micol.herdr-bridge` | 0.1.0, 49 installs | `clement-micol/herdr-bridge`, MIT, 0 stars | 2026-08-21 | 1 | VS Code extension | Fires a `vscode://` URI from a herdr keybinding to open the pane's file in VS Code. Contributes **no views** |
| `endoumame.herdr-vscode` | 0.2.3 | `endoumame/herdr-vscode`, MIT, 0 stars | 2026-08-03 | 1 | VS Code extension, `extensionKind: ["workspace"]` | Inline review comments in VS Code, queued and handed as a batch to an agent in herdr. Contributes one SCM view |

**The two lines that matter most, both answered in the negative.**

1. **No add-on reads `~/.claude/sessions/<pid>.json`.** A grep for
   `claude/sessions` across all eleven repos returns nothing. Every one of them
   consumes herdr's own agent detection over its socket or plugin API, so none
   of them gives herdr hook-free truthful status from Claude's registry. If
   that property is wanted on top of herdr it has to be built.
2. **No add-on writes to `~/.claude`.** A grep for `claude/settings` and
   `.claude/hooks` across all eleven returns nothing. The whole ecosystem is
   clean on the penalised line — unlike `a9a4k.deck`.

One more environment note found while confirming herdr's identity, relevant to
the option already ranked first: **herdr's native Windows support is generally
available**, installed with a PowerShell one-liner and built on ConPTY instead
of the Unix PTY model, with some capabilities still platform-dependent. Its
docs also treat WSL as an exercised path, naming "Windows WezTerm hosting Herdr
through WSL" and a WSL-specific cursor default
(`docs/preview/website/src/content/docs/windows-beta.mdx:85,93`).
## Ranked, both passes combined

1. **`daintreehq/daintree` 0.36.1** (was Canopy IDE) — clears all eight
   rejects, reaches WSL from a Windows build on purpose, refuses to delete a
   workspace holding a live agent, and exposes dispatch over MCP. Costs:
   liveness is derived from PTY output rather than the session registry, and it
   only sees sessions it launched.
2. **`asheshgoplani/agent-deck`** — the cleanest shell dispatch of any
   candidate (`agent-deck add . -c claude --worktree … --new-branch`), Codex
   verified, reads Claude's live registry, MIT, pushed daily. Costs: the rail
   is a TUI plus a browser tab, not the window Chris already has open, and MCP
   attach rewrites `~/.claude/settings.json`.
3. **`a9a4k.deck` 0.24.0** — the best of the VS Code class and the only one in
   it covering both CLIs; status for every registered repo regardless of the
   active folder. Costs: installs nine Claude hooks and five Codex hooks into
   `~/.claude/settings.json` and cannot report status without them, needs a
   tmux-naming wrapper for shell dispatch, never warns that a worktree it is
   deleting has a live agent in it, and a worktree click replaces the
   multi-root window with a single folder.
4. **`zarritas.agent-sessions` (Aterm) 1.3.0** — seven agents, a Rust CLI, and
   the most truthful liveness read in either pass. Weaker as a repo rail, live
   status Claude-only today, closed Pro module.
5. **`inthepond.agent-view-for-claude-code` 0.9.2** — the best discovery of
   shell-started sessions with no glue at all, scanning every project under
   `~/.claude/projects`. Claude-only, and installs a hook for Hold.
6. **`vana123.vswt` 0.4.0** — matches Chris's `<repo>/.claude/worktrees/`
   convention and registry-based liveness exactly, writes nothing. Pre-alpha,
   Claude-only, no release since 2026-06-01.
7. **`mkellerman.herdex` 0.1.0** — puts herdr's rail inside VS Code and adds no
   new runtime. v0.1.0, one commit, 2s status polling.

## Does any of this change the ranking #704 starts from?

**Yes — the second pass changes it, where the first pass did not.** The decision
ticket starts from herdr, then VS Code + extension, then a self-built page, with
Pane rejected by trial. Three changes, in order of how much they matter.

- **Daintree belongs in the first position alongside herdr, and the two should
  be trialled head to head.** It is the only candidate in this ticket that is
  simultaneously a Windows app that deliberately reaches WSL, a runner of the
  CLIs Chris chose (Claude Code and Codex, named first of seventeen), a rail
  ordered by which agent needs him, a batch-review surface with no per-ticket
  gate, a bulk GitHub-issue-to-worktree pipeline matching the wayfinder flow,
  and a scriptable control plane. Herdr keeps two advantages: it is a far more
  established project, 37,989 stars against 71, and its status detection does
  not depend on reading a terminal. Daintree keeps two of its own: the review
  and merge half of the loop, which herdr does not have without the
  `herdr-reviewr` plugin, and the refusal to delete a workspace holding a live
  agent. That is a genuine contest, not a re-ranking on paper, and the brief's
  own rule applies — trial the top two where a trial costs under an hour.
- **"VS Code + extension" gets a named best occupant, and it is `a9a4k.deck`.**
  That slot previously meant VS Code plus `anthropic.claude-code`, which
  supplies no rail. Deck supplies a cross-repo worktree tree, terminals that
  survive reload and reboot, status for both CLIs across every registered repo,
  and needs-input notifications, off the shelf. It is third overall rather than
  first because of the `~/.claude/settings.json` hook write it cannot work
  without, the wrapper shell dispatch needs, and the single-folder switch.
- **The self-built page should drop below where it sits.** Everything it was
  going to be built for now exists in something maintained: the session
  registry read with a real pid probe in Aterm's Rust CLI and in `vswt`,
  cross-repo session discovery in `inthepond.agent-view`, and a scriptable rail
  in `asheshgoplani/agent-deck`. If a page is still wanted, `aterm live` and
  `agent-deck web` are both usable data sources, which lowers that option's
  maintenance line as well as its appeal.
- **Two herdr add-ons are worth adopting whichever way the top choice goes**, on
  scored lines herdr does not cover: `persiyanov/herdr-reviewr` for file open
  and diff from the rail, and `dcolinmorgan/herdr-remote` for notification when
  an agent is waiting. Neither is first-party, both are one-maintainer, and
  neither touches `~/.claude`.
- **`BradenTerry.agent-worktrees` stays confirmed dead for this workflow**, at
  `src/worktreeData.ts:245`, with no multi-root mode present or planned.

## Unverified

- **Nothing was installed, launched, or trialled in either pass.** Every finding
  is from a manifest, a README, a published doc, or source read in a shallow
  clone. The brief's trial-run step is still open, and it now has a clear
  target: Daintree against herdr, on the WSL path specifically.
- **Daintree's WSL support is verified in source, not on this machine.** The
  `wsl.exe git` routing, distro targeting and 9P path translation are read from
  `electron/utils/hardenedGit.ts`; whether the agent PTY itself lands in WSL
  (as opposed to git alone) was not established, and it is the first thing a
  trial should check.
- **Daintree's exact MCP tool count per tier was not enumerated.** The 441
  registry ids, 128 documented tool ids and 32-entry unbound manifest are
  counted from source, but which tools a given authorization tier actually
  exposes to a shell was not resolved, and it decides how much of dispatch is
  reachable without the GUI.
- **Daintree's licence is ambiguous.** The site says Apache 2.0; the GitHub API
  reports `NOASSERTION` for the repo as of 2026-09-12. Worth pinning before
  adopting.
- **Deck on WSL is unproven**, and the tmux wrapper recipe in this document is
  read from source, not run. That a shell-created session on the `deck` socket
  named `wt-…__term-N` with `DECK_SESSION` set appears as a row and carries
  status is inferred.
- **Neither `agent-deck` nor Daintree was checked for adopting an agent it did
  not start.** Both are expected to dispatch rather than adopt; for `agent-deck`
  that is fine because dispatch is a shell command, but the case where a worker
  is started outside the tool was not tested for either.
- **Aterm's Community-versus-Pro split and price were not determined**, nor was
  which scored features fall on which side.
- Install counts and star counts are marketplace and GitHub API values read
  2026-09-12, and are a weak proxy for maintenance in a class this young.
- Four extensions were scored partly from README text because they publish no
  source: `petar-s-dimov.argus-worktree-agent-sessions`,
  `barakolsheviz.agent-forq`, `experlab.100doo`, `kendr.kendr-code-vscode`.
  Each is rejected on a stated line, but none meets the #488 evidence standard
  and none should be revived without source.
- `web3dev1337/agent-workspace` could not be found and is unscored.
