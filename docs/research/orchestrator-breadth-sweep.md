# Breadth sweep: what orchestrators exist that we never scored?

Ticket: [#486](https://github.com/caneff/agent-skills/issues/486)
Corrects on breadth: [#485](https://github.com/caneff/agent-skills/issues/485)
(`docs/research/burn-down-hosts.md`, branch `research/burn-down-hosts`)

#485 scored its candidates well but never swept for candidates outside the list
it inherited from #478. This document supplies the sweep. It does **not** repeat
#485's scoring — where a candidate was already killed there, it is named and
cross-referenced, not re-argued.

Primary sources only: the tool's own repo, its own docs site, its own release
notes, its own source. Where a source does not say, this says **not documented**
and names what was checked. Two claims below were checked against a *second*
first-party source because the first one was a docs-site LLM answerer rather
than a static page; both are flagged where that happened.

---

## Bottom line

**Nothing beats staying on Claude Code. The breadth was swept and it held.**

Four tools survived the hard rejects, all four of them new to this map:
**Nimbalyst**, **repomon**, **agent-deck**, and **Sculptor**. All four run
Claude Code itself, so the skills survive in all four. All four beat Claude
Code on exactly one line — **requirement 4, the workspace made at launch** —
which is Claude Code's one documented defect and the one #478 already has a
workaround for.

And buying that line costs the deletion policy. Claude Code's is lock-based and
liveness-aware, documented, and is the only one in the whole survey that is.
repomon's was read in its own source and is **not** liveness-aware: it shells
out to `git worktree remove` without `--force` and never sets a lock, so a clean
worktree with a live agent reading it can be removed — the exact `t294` failure
that opened this map. The other three do not document a deletion policy at all.

So the trade on offer is: gain a worktree at launch (already worked around),
lose the one guard that was the reason for the map. That is not a trade. Stay on
Claude Code.

The genuinely new information is that a cross-repo *fleet* category now exists
and did not when #478 assembled its list. If the `claude agents` view ever
regresses on requirement 1, **repomon** and **agent-deck** are the two to look
at again — both explicitly built for many repos at once, both on Linux, both
running the real Claude Code binary.

---

## Phase 1 — the names, before any scoring

Sweep phrasings used: Claude Code wrappers/GUIs; agent orchestrators; agent task
queues; git-worktree managers for agents; cross-repo agent dashboards; "fleet"
/ "mission control" framings; background-agent platforms. Name sources included
two first-party curated indexes —
[andyrewlee/awesome-agent-orchestrators](https://github.com/andyrewlee/awesome-agent-orchestrators)
(194 entries) and
[bradAGI/awesome-cli-coding-agents](https://github.com/bradAGI/awesome-cli-coding-agents).
Those indexes were used **only to harvest names**; every factual claim below
comes from the named tool's own repo, docs, or source.

**From the ticket's starting list:** Nimbalyst, Cursor background agents (now
"Cloud Agents"), OpenHands, Sculptor, Terragon, Factory, Charlie, Amp, Zed agent
panel.

**Found by the sweep, cross-repo or Claude-Code-hosting candidates:**
repomon, agent-deck, agent-console (ms2sato), Xum (`coder/mux`), Emdash,
superset, agent-of-empires, jean, kandev, automaker, Berd (Block), Orca
(Stably), Paseo, herdr, amux, dmux, cmux, octomux, openkanban, jat, clideck,
Garcon, Open Session, tlbx, intentic, Proliferate, t3code, humanlayer,
constellagent, diri, Fletch, supacode, Tortie, Waku, clave, aizen, Alethe,
Aperant, Comet, CodeNomad, Tempest, Traycer, vibe-tree, parallel-code, mux
(coder), Zaivern Code, agent-manager, agent-orchestrator (Untrivial),
ai-maestro, agentbox, thurbox, tmux-ide, agterm, agent-squid, AGX, bb, Better
Agent, Claude Command Center, collaborator, dorothy, GraphCode, IM.codes,
ivy-tendril, omg.dev, OpenChamber, Ouijit, qm, supacode, synara, takopi,
vibecraft, Conduit, Toad, crew, kanban-code, Emerge code-factory, Pane
(runpane), CodeAgentSwarm, multiclaude, gastown, paperclip, Claude Code Kanban
(NikiforovAll), kanban-code (langwatch), gwq, agentree, git-worktree-runner
(CodeRabbit), worktree-cli, ccswarm, parallel-worktrees, agent-worktree,
agenttools/worktree, fleet (oguzhnatly), claude-fleet, agent-fleet-o.

**Task-runner / ticket-driven candidates:** cyrus, sortie, lalph, Contrabass,
symphony (OpenAI), open-swe (LangChain), gh-aw (GitHub), aeon, NEEDLE, multica,
Taskuary, remote-swe-agents (AWS), awslabs/cli-agent-orchestrator,
claude-code-action, background-agents, Codegen, Claude Code on the web,
Agent 37, GitHub Copilot coding agent app.

**Already scored in #485, listed for completeness, not re-scored:**
`claude agents` view, Claude Code desktop app, Claude Code CLI, Claude Squad,
Vibe Kanban, Crystal, uzi, container-use, Conductor, Devin, Jules.

That is the full harvest. Scoring starts below.

---

## Phase 2, step 1 — the hard rejects

Applied in the ticket's order. Analysis stops at the first line a tool dies on.

| Tool | Dies on | Source |
|---|---|---|
| **agent-console** (ms2sato) | (a) macOS-only | Its README's own top-line note: "Currently only tested on macOS & Claude Code." ([repo](https://github.com/ms2sato/agent-console)) |
| **Conductor** | (a) macOS-only | Confirmed already in #485; the new hard reject in this ticket resolves it from "could not determine" to out. ([conductor.build](https://conductor.build/docs/concepts/workflow)) |
| **Terragon** | (b) dead | Shut down. Its own site now serves a page titled "Terragon Shutdown" ([terragonlabs.com](https://www.terragonlabs.com/)); the service ended **9 February 2026** ([docs.terragonlabs.com/docs/resources/shutdown](https://docs.terragonlabs.com/docs/resources/shutdown) — note that host's TLS certificate has expired, so this was read via the search index and corroborated below). The code survives only as an archive: "This repository is an open-source snapshot of Terragon at the time of shutdown. It is provided **as-is**, with no guarantees of maintenance, support, or completeness." ([terragon-labs/terragon-oss](https://github.com/terragon-labs/terragon-oss)) |
| **Crystal** | (b) dead | Deprecated Feb 2026, superseded by Nimbalyst. Already established in #485. ([repo](https://github.com/stravu/crystal)) |
| **Vibe Kanban** | (b) sunsetting | Its own README's sunset notice. Already established in #485. ([repo](https://github.com/BloopAI/vibe-kanban)) |
| **uzi** | (b) dead | No commit since June 2025. Already established in #485. |
| **Cursor Cloud Agents** (the renamed background agents) | (c) own agent | "Cloud agents use the same [agent fundamentals] but run in isolated VMs in the cloud." No external CLI is named anywhere on the page. ([cursor.com/docs/cloud-agent](https://cursor.com/docs/cloud-agent)) **Worth recording:** it *does* clear requirement 1 outright — "Cloud agents can also run in multi-repo environments. Use one when a task spans separate frontend, backend, infrastructure, or shared-library repositories." It still dies on requirement 3. |
| **Factory** (Droid) | (c) own agent | "Install Droid, delegate your first task, and scale from a single session to an automated SDLC." Claude Code is not mentioned anywhere in the docs. ([docs.factory.ai](https://docs.factory.ai/)) |
| **Amp** | (c) own agent | "the frontier agent. It is a coding agent and a development environment" — its own harness, its own multi-model support, no dependence on Claude Code. ([ampcode.com/manual](https://ampcode.com/manual)) |
| **Charlie** | (c) own agent | A hosted agent with its own GitHub account, running on OpenAI models: "Charlie now runs on OpenAI's GPT-5 … inside your GitHub, Slack, and Linear workflows." ([charlielabs.ai](https://charlielabs.ai/blog/charlie-2025-a-recap-and-whats-next/)) |
| **Xum** (`coder/mux`, renamed from Mux) | (c) own agent | "Xum has a custom agent loop but much of the core UX is inspired by Claude Code." Inspired by is not is. ([repo](https://github.com/coder/mux)) |
| **OpenHands** | (d) multi-repo not documented | Survives (c) — it can host Claude Code over ACP: "Run Claude Code, Codex, or Gemini CLI in Agent Canvas through the Agent Client Protocol," launching `npx -y @agentclientprotocol/claude-agent-acp` as a subprocess ([acp-agents](https://docs.openhands.dev/openhands/usage/agent-canvas/acp-agents.md)). But requirement 1 is **not documented**: the Conversations page describes per-launch repository and branch selection and says nothing about whether the conversation list spans repositories ([conversations](https://docs.openhands.dev/openhands/usage/agent-canvas/conversations.md)). Checked: the docs index, the Agent Canvas conversations page, the backends page, the repository-customization page. Cannot be cleared; recorded as a gap, not a pass. |
| **Zed agent panel** | (d) not documented | The external-agents page covers starting agents and managing threads but "does not address whether the Agent Panel is scoped to a single project or spans multiple repositories." ([zed.dev/docs/ai/external-agents](https://zed.dev/docs/ai/external-agents)) Checked the external-agents page; `zed.dev/docs/workspace` 404s. Not cleared, not rejected. |

**Not scored, and why:** the long Phase 1 tail (Emdash, superset, jean, Orca,
Paseo, herdr, gwq, cyrus, sortie, symphony, open-swe, gh-aw, the ~60 desktop
apps in the awesome list, and the rest) presents no first-party claim of running
agents across several repositories in one surface. Requirement 1 is the ticket's
first hard reject and the cheapest to test, and none of them make the claim.
Scoring each individually would cost more than it can return; they are recorded
by name so the next sweep does not have to re-find them. Two named in Phase 1
were **not** verified from a primary source — `kanban-code` (reported as a
native macOS app) and `Pane` — and are deliberately left unscored rather than
rejected on hearsay.

---

## Phase 2, step 2 — the survivors

Four. All run Claude Code itself.

| | 1. 4-5 repos, one surface | 2. Linux/WSL2 | 3. Runs Claude Code | 4. Workspace at launch | 5. Batch review | 6. Foreign tickets | 7. Deletion policy | Land on `main`, no PR |
|---|---|---|---|---|---|---|---|---|
| **repomon** | **PASS** — built for it | PASS | PASS — real terminal | **PASS** | PASS — never makes a PR | free text (no integration) | **FAIL** — not liveness-aware, proven in source | Yes (`lane.merge`) |
| **agent-deck** | **PASS** | PASS (incl. WSL) | PASS | **PASS** | PASS — never makes a PR | free text (no integration) | not documented | Yes (`worktree finish` merges locally) |
| **Nimbalyst** | **PASS** — via the rail | PASS | PASS | **PASS** | PASS | **PASS** — imports GitHub issues | not documented | not documented |
| **Sculptor** | **PASS** — via tabs | PASS | PASS, with adaptation | **PASS** | not documented | not documented | not documented | not documented |
| *(incumbent)* **`claude agents`** | PASS (verified live, #485) | PASS | is Claude Code | **FAIL** — moves on first write | PASS | free text | **PASS** — lock-based, liveness-aware | Yes |

### repomon

[github.com/AliHamzaAzam/repomon](https://github.com/AliHamzaAzam/repomon) —
Rust, Apache-2.0, TUI + Tauri desktop app.

**1. Multi-repo: PASS, and it is the whole premise.** "Mission control for a
fleet of AI coding agents across all your repos … Many repos × many worktrees ×
many agents, on one screen." It names the alternative explicitly: "Other tools
run parallel agents in *one repo, many worktrees* (Claude Squad, Conductor,
Crystal, ccmanager). repomon is built for the developer juggling **5-15 active
projects**." Its own comparison table scores `claude agents` as "one tool, flat
list" against repomon's "many repos × worktrees × agents." The sidebar "groups
lanes (repo + worktree) by project, sorts by recent activity, and floats the
ones waiting on you."

**2. Linux: PASS.** `.AppImage`, `.deb`, and `.rpm` in every release; the
architecture note says the runtime is "tmux on macOS/Linux."

**3. Runs Claude Code: PASS, and more literally than any other survivor.** It
spawns the agent as `tmux new-window -t repomon -n lane-7 -c <worktree>
'<agent-binary> [task]'` and says of the resulting pane: "This is a *genuine
terminal* — there is **no difference** from running the agent in a [normal
terminal]" ([docs/agents.md](https://github.com/AliHamzaAzam/repomon/blob/main/docs/agents.md)).
The agent is whatever binary you configure, e.g. `claude-yolo = "claude
--dangerously-skip-permissions"` in `~/.config/repomon/config.toml`. It also
**adopts sessions you started yourself**: a Claude session running in a
registered repo's worktree "is **detected automatically** — its status and
'needs you' show up." Nothing is intercepted, so CLAUDE.md, skills, hooks and
settings behave exactly as they do today.

**4. Workspace at launch: PASS.** A lane *is* repo + worktree, created before
any agent exists: `repomon lane new --repo pos-saas --branch feat/inventory
--source main`, then agents are spawned with `-c <worktree>` into a directory
that already exists. `lane.rs` confirms: "`create` runs `git worktree add`."

**5. Batch review: PASS.** No PR is ever created. `lane.merge { lane_id, into? }`
merges a lane's branch; `lane.diff` returns "commits ahead of the repo's base
branch (with diffstat) plus uncommitted state"
([docs/protocol.md](https://github.com/AliHamzaAzam/repomon/blob/main/docs/protocol.md)).
Review N lanes in one sitting, merge as you like. No interactive per-ticket
gate — the opposite: the built-in orchestrator (`repomind`) "defaults to
`autonomous`" and "may create, merge, and delete lanes and run a goal end-to-end
without asking first."

**6. Foreign tickets: no integration documented.** Grepped the README, agents
doc and protocol doc for issue/ticket/tracker: zero hits. This is the same
posture as the Claude Code CLI — the dispatch input is a free-text task string
appended to the agent command, so a `gh` lookup works, but there is nothing to
cite as a feature.

**7. Deletion: FAIL, and this is the finding that decides the ticket.** The
protocol exposes `lane.delete { lane_id, also_delete_branch=false }` with no
liveness condition stated. Read in source, `LaneService::delete` looks up the
lane, refuses only the main worktree, and calls `worktree::remove(&rp, &wp,
false)`
([lane.rs](https://github.com/AliHamzaAzam/repomon/blob/main/crates/repomon-core/src/lane.rs)).
That third argument is `force`, and `remove_args` only appends `--force` when it
is true
([git/worktree.rs](https://github.com/AliHamzaAzam/repomon/blob/main/crates/repomon-core/src/git/worktree.rs)).
So the only protection is whatever plain `git worktree remove` gives you: it
refuses a *dirty* or *locked* worktree. repomon never sets a lock of its own,
and never checks whether an agent is attached. **A clean worktree with a live
agent reading it is removable.** The one softener is at the orchestrator layer,
not the API: repomind uses "a two-phase human-confirmation flow for lane
deletion (the first call only returns an impact summary and a token; the delete
only happens once that token comes back)" — a confirmation, not a liveness
guard, and it does not cover `repomon lane delete` or `lane.delete`.

**Land on `main` with no PR:** Yes. `lane.merge` merges into the base branch;
nothing pushes or opens a PR.

**Maintenance:** active but thin. Apache-2.0, created 29 May 2026, last push
**29 Aug 2026**, latest release **v0.8.1 on 29 Aug 2026**, not archived — but
**17 stars and a single maintainer**, pre-1.0, and its own headline feature
(repomind) is labelled "**Status: functional, not polished** … Treat it as an
early feature, not a finished one." Bus factor one.

### agent-deck

[github.com/asheshgoplani/agent-deck](https://github.com/asheshgoplani/agent-deck)
— MIT, TUI.

**1. Multi-repo: PASS.** "**Agent Deck is mission control for your AI coding
agents.** Running Claude Code on ten projects, OpenCode on five more, another
agent somewhere in the background? One terminal shows every session — running,
waiting, or done — and one keystroke switches between them." That is
requirement 1's second clause verbatim. It also has the triage surface the
burn-down wants: "Press `/` to fuzzy-search across all sessions. Filter by
status with `!` (running), `@` (waiting), `#` (idle), `&` (error)."

**2. Linux/WSL2: PASS, stated explicitly.** "**Works on:** macOS, Linux, Windows
(WSL)."

**3. Runs Claude Code: PASS.** Sessions are Claude Code processes in tmux panes
(`agent-deck add . -c claude`), and it is skills-aware rather than
skills-hostile: "Attach/detach Claude skills per project with a managed pool
workflow … Apply writes project state to `.agent-deck/skills.toml` and
materializes into `.claude/skills`."

**4. Workspace at launch: PASS.** `agent-deck add . -c claude --worktree
feature/a --new-branch` "creates a session in a new worktree" — one command,
worktree first. It also copies gitignored files in per a `.worktreeinclude`
file, and notes this "Matches [Claude Code Desktop
semantics](https://code.claude.com/docs/en/worktrees#copy-gitignored-files-into-worktrees)."

**5. Batch review: PASS.** It never creates a PR. `agent-deck worktree finish
"My Session"` "merges the branch, removes the worktree, and deletes the
session." Batching is your business, unchanged.

**6. Foreign tickets: no integration documented.** Grepped for issue/ticket/
tracker: the only `gh` usage documented is a guarded PR-comment poster, not
ingest. Free text, same as the CLI.

**7. Deletion: not documented.** Two commands exist — `worktree finish`
(merges, removes, deletes the session) and `worktree cleanup`, which "finds and
removes orphaned worktrees." Neither the README nor the worktree section states
what makes a worktree "orphaned," whether a running agent blocks removal, or
whether `--force` is used. Checked: the README's Git Worktrees section, its
config reference, and the tmux/socket section. A separate container setting
(`auto_cleanup = true`, "Remove containers when sessions end") is
session-lifecycle-aware, but that governs containers, not worktrees. Recorded
as a gap.

**Land on `main` with no PR:** Yes — `worktree finish` merges locally.

**Maintenance: the best of the four.** MIT, created 3 Dec 2025, last push
**31 Aug 2026**, latest release **v1.15.0 on 23 Aug 2026** (v1.14.0 the day
before — a fast cadence), **821 stars**, past 1.0, and actively recruiting
co-maintainers ("If you've had a couple of PRs land here and want to help steer
… open an issue titled 'maintainer: your area'").

### Nimbalyst

[github.com/nimbalyst/nimbalyst](https://github.com/nimbalyst/nimbalyst) — MIT,
Electron desktop app. Crystal's designated successor, which #485 named and never
evaluated.

**1. Multi-repo: PASS — but only after a contradiction was resolved.** The
static FAQ page answers the multi-workspace question the *wrong* way for this
requirement: "**Can I have multiple workspaces open?** Yes, unlimited windows.
Each workspace is independent. Switch with window shortcuts."
([faqs](https://docs.nimbalyst.com/faqs/faqs.md)) That is the five-windows
failure mode. The docs-site answerer claimed the opposite. The tiebreak is the
first-party release archive, and it backs the pass:

> **Multi-Project Left Rail** — A new Discord-style vertical rail lets a single
> Nimbalyst window host several workspaces side-by-side, with instant switching.
> Inactive projects stay warm: AI sessions keep streaming. Cmd/Ctrl+1..9
> activates the Nth project; Cmd/Ctrl+Shift+W closes the active one. Turn this
> on in User Settings > Advanced > General.

(v0.60.1, 13 May 2026,
[release-announcements](https://docs.nimbalyst.com/getting-started/release-announcements.md))
Note the feature is **off by default**. Note also what it is not: a later
changelog entry reads "In Multi-Project mode, a project's tracker list no longer
shows another open project's items" — there is no merged all-repos list. It
passes requirement 1 on the *switching* clause, not the one-view clause. The
"Agent attention list" added in v0.70.5 — "a grouped attention list for sessions
awaiting input, running, or unread" — is the triage surface, but it is
per-project.

**2. Linux: PASS.** "Free, MIT-licensed desktop app for macOS, Windows, Linux,
with mobile companion for iOS and Android" — Linux ships as an AppImage.

**3. Runs Claude Code: PASS, stated plainly.** "Nimbalyst runs on top of Claude
Code and Codex rather than replacing them."
([coding-with-claude-code](https://docs.nimbalyst.com/developer-features/coding-with-claude-code-and-nimbalyst.md))
Corroborated by the FAQ — "Can I use my existing Claude Code custom commands?
Yes" — and by dedicated docs for `/` commands and skills and for importing
existing Claude Code sessions.

**4. Workspace at launch: PASS.** "From a Tracker item, choose the worktree
action to launch an isolated session with that item linked as its context," and
"Create a worktree from the Agent Mode UI to start an isolated AI session on a
new branch." ([worktrees](https://docs.nimbalyst.com/developer-features/worktrees.md))
The worktree precedes the session in both paths.

**5. Batch review: PASS.** No mandatory per-ticket gate. The one interactive
gate that exists — commit proposals — is explicitly defeatable: "Skip the manual
approval step for git commit proposals … When enabled, Claude's commit proposals
are committed automatically without waiting for your approval."
([working-with-git](https://docs.nimbalyst.com/developer-features/working-with-git.md))

**6. Foreign tickets: PASS — the only survivor that documents it.** "Nimbalyst
can import GitHub issues as tracker items," via the `nim` CLI:
`nim tracker import search github-issues --repo owner/repo --state open` and
`nim tracker import github-issues "owner/repo#42" --type bug`
([nim-cli](https://docs.nimbalyst.com/task-management/nim-cli.md)). It is a
one-way import into Nimbalyst's own tracker, not a live sync — and it requires
the app to be running. Note the shape mismatch with this workflow: the tickets
are authored by wayfinder on GitHub and would have to be pulled into a second
tracker to drive a session from them.

**7. Deletion: not documented.** The worktrees page describes creation and use
and says nothing about removal. The docs answerer pointed at auto-archiving that
"can skip confirmation when the branch is clean and merged," but no static page
was found stating the deletion signal, and nothing anywhere states whether
removal is blocked while an agent is running. Checked: the worktrees page,
working-with-git, and the release archive. Recorded as a gap.

**Land on `main` with no PR: not documented.** Git operations (commit, push,
pull, fetch) are exposed and a PR-review mode exists, but nothing states that
committing straight onto `main` without a PR is supported or blocked.

**Maintenance: the strongest of the four.** MIT, **1,625 stars**, last push
**31 Aug 2026**, latest release **v0.76.0 on 31 Aug 2026** with v0.75.5 three
days earlier. Nineteen dated releases in the archive between Feb and Aug 2026.
Still pre-1.0.

### Sculptor (Imbue)

[github.com/imbue-ai/sculptor](https://github.com/imbue-ai/sculptor) — MIT,
desktop app, container-per-agent.

**1. Multi-repo: PASS, via tabs.** "Click the **+** button at the top of the
Sculptor window. Choose a repository … Each workspace gets its own tab;
switching tabs switches repos"
([workspaces](https://github.com/imbue-ai/sculptor/blob/main/docs/help/workspaces.md)).
One window, N repos, tab-switching — requirement 1's second clause. Note that a
workspace is scoped to one repo ("an isolated working copy of **one**
repository, on its own branch"), so like Nimbalyst this is switching, not a
merged view.

**2. Linux: PASS.** Downloads for "Mac (Apple Silicon)," "Linux," and "Linux
ARM64." The product page states "Mac (Apple Silicon) and Linux. No Windows or
mobile support currently" — WSL2 is not named either way, but a native Linux
build is what this machine needs.

**3. Runs Claude Code: PASS, with adaptation — the caveat matters.** "Sculptor
runs Claude Code as a streaming JSON process with its control protocol enabled,"
and the harness page's "Not available" section reads, in full: "Nothing. Claude
Code supports every capability described above." But it is not an untouched
Claude Code: Sculptor "disables Claude's built-in Ask User Question and Exit
Plan Mode tools, and registers replacements of its own," adds its own system
prompt text, "loads three of its own plugins," and registers a pre-compaction
hook
([integrated_harnesses](https://github.com/imbue-ai/sculptor/blob/main/docs/help/integrated_harnesses.md)).
It also ships an opinionated pipeline of its own — `spec → mock → architect →
plan → build → review` — which overlaps and competes with the wayfinder →
to-spec → to-tickets → implement pipeline this workflow already has
([skills](https://github.com/imbue-ai/sculptor/blob/main/docs/help/skills.md)).
Skills as files should survive; the harness around them does not stay stock.

**4. Workspace at launch: PASS.** A workspace — "a git worktree off your repo"
— is created by the **+** button *before* the agent starts, optionally with a
starter prompt. A "Clone" mode (a full separate clone) and an "In-place" mode
(no isolation at all) are also offered.

**5. Batch review: not documented.** A `pull_requests.md` help page exists and a
`/review` slash command ships, but nothing states whether review is a mandatory
gate or whether many workspaces can be merged in one sitting. Checked the help
index, workspaces, agents, skills and harnesses pages. Not cleared.

**6. Foreign tickets: not documented.** No issue-tracker integration appears in
the help docs. Checked the help index.

**7. Deletion: not documented.** The workspaces page covers creation, branches
and modes; it does not state what removes a workspace, on what signal, or
whether a running agent blocks it. Recorded as a gap.

**Land on `main` with no PR: not documented.** The docs describe bringing
changes "directly to your on-disk repo" from a clone-mode workspace, but do not
address committing straight to `main`.

**Maintenance: active, but self-declared experimental.** MIT, **221 stars**,
last push **1 Sep 2026**, latest release **sculptor-v0.46.0rc1 on 1 Sep 2026**
(v0.45.0 on 26 Aug). Against that, its own README: "Sculptor is actively under
development and should be treated as an **experimental research preview** …
Things may change quickly and significantly."

---

## What this changes about #485's answer

Nothing about the conclusion; two things about its support.

**#485's conclusion is now supported on breadth.** It was reached from an
inherited list. Four tools it never saw have now been scored from primary
sources, and none of them displaces Claude Code.

**One of #485's "could not determine" lines is now closed.** Conductor is out,
on the new macOS-only hard reject.

**And requirement 4 is now a known, priced gap rather than a unique defect.**
Four independent tools create the worktree at launch. Claude Code is the outlier
on that line — but it is the only one of the five with a documented,
liveness-aware deletion policy, and repomon's source proves that at least one of
the four is strictly worse there. #478's pre-made-worktree workaround remains
the cheaper fix.
