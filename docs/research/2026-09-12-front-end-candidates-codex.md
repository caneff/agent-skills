# Front-end candidates after Orca — Codex pass

Research date: 2026-09-12. This is an independent pass for #707. I did not
read #706 or `research/front-end-claude`. The requirements brief is the
authority for meanings of `pass`, `fail`, and the numbered hard-reject lines.
`—` means the row did not reach that test. Sources are first-party product
pages, the owner's repository at the pinned commit, or the locally installed
product manifest where that is the available primary evidence. GitHub search
and awesome-list style discovery were used only to find names, not as evidence
for capability claims.

## Phase 1 — names found, before scoring

The sweep found **73 named entries** (including the brief's explicit names,
the Crystal/Nimbalyst legacy alias, and separately named same-name projects).

| Class | Names found |
| --- | --- |
| Editors with agent panels | [VS Code + Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code), [Cursor](https://www.cursor.com/), [Zed](https://zed.dev/docs/ai/agent-panel), [JetBrains + Junie](https://www.jetbrains.com/junie/), [Windsurf](https://windsurf.com/editor), [Trae](https://www.trae.ai/), [Kiro](https://kiro.dev/), [Google Antigravity](https://antigravity.google/), [Cline](https://github.com/cline/cline), [Roo Code](https://github.com/RooCodeInc/Roo-Code), [Continue](https://github.com/continuedev/continue), [PearAI](https://github.com/trypear/pearai-master), [Void](https://github.com/voideditor/void) |
| Orchestrator desktop apps | Orca 1.4.197 (baseline); [Conductor](https://conductor.build/), [Nimbalyst](https://github.com/nimbalyst/nimbalyst), Crystal (legacy Nimbalyst; [source](https://github.com/stravu/crystal)), [Sculptor](https://sculptor.ai/), [Daintree](https://github.com/daintreehq/daintree), [HyprDesk](https://github.com/HyprDesk/hyprdesk), [ai-14all](https://github.com/ai-creed/ai-14all), [VibeTree](https://github.com/sahithvibudhi/vibe-tree), [Arbor/penso](https://github.com/penso/arbor), [Braid](https://getbraid.dev/), [cc-haha](https://github.com/NanmiCoder/cc-haha), [Code-Bar](https://github.com/For-Tr/Code-Bar), [Tidebreak](https://github.com/brightwave-inc/tidebreak), [Coppice](https://github.com/iamfozzy/coppice), [Xuanpu](https://github.com/slicenferqin/xuanpu), [Klaussy Desktop](https://github.com/steph-dove/klaussy-desktop), [Topics](https://github.com/armonia/topics-app), [Astera](https://github.com/parsingk/Astera), [Vibe Manager](https://github.com/9cb14c1ec0/vibe-manager), [Claude Orchestrator Desktop](https://github.com/paurodriguez0220/claude_orchestrator-desktop), [Sequoias](https://github.com/gongiskhan/sequoias), [Dashpod](https://github.com/Leonard1706/dashpod), [Herd](https://github.com/bethandutton/herd), [Ziro Code](https://github.com/dhirajlochib/ziro-code), [Maestro/stroland02](https://github.com/stroland02/Maestro), [Conductor-arch](https://github.com/perceo-ai/conductor-arch), [Yolium Desktop](https://github.com/cpotech/yolium-desktop), [Patchyard](https://github.com/bigmacfive/Patchyard), [Agent Tarn](https://github.com/whichxjy/agent-tarn), [Crowbar](https://github.com/char2cs/crowbar), [TeamCow](https://github.com/chobitsX/teamCow), [Arbor/bps2414](https://github.com/bps2414/arbor), [Kine Agent](https://github.com/sharankarthikyan/kine-agent), [Coding Canvas](https://github.com/ethantheDeveloper220/coding-canvas), [Maestro/xOAviOx](https://github.com/xOAviOx/maestro), [Polaris](https://github.com/KevinBonnoron/polaris), [AI Sidekicks](https://github.com/Sawmonabo/ai-sidekicks), [NexusOps](https://github.com/SiWarlock/NexusOps), [Grove](https://github.com/ShebinKMohan/Grove), [DESK](https://github.com/eliasribeiro/DESK.CodeWorkspaceOrchestrator), [Mozzie](https://github.com/usemozzie/mozzie), [Universal Agent Manager](https://github.com/davidtaylor6130/Universal-Agent-Manager), [SigmaLink](https://github.com/rokipet/SigmaLink), [Codex Fleet](https://github.com/benjamin05wilson/codex-fleet), [Jig](https://github.com/guicybercode/Jig), [DSH Desktop](https://github.com/HQfire/dsh-desktop), [Swarm](https://github.com/ABCrimson/Swarm), [Vicoa](https://github.com/vicoa-ai/vicoa), LoopTroop (GitHub-search discovery only; no owner source located, therefore H1 reject) |
| Terminal tools | [Claude Code / Agent Teams](https://code.claude.com/docs/en/agent-teams), [Claude Squad](https://github.com/smtg-ai/claude-squad), [dmux](https://github.com/standardagents/dmux), [Gas Town](https://github.com/gastownhall/gastown), [OpenOrchestrator](https://github.com/gitpcl/openorchestrator), [ateam](https://github.com/clawnify/ateam), [opentree](https://github.com/axelgar/opentree), [shep-ai CLI](https://github.com/shep-ai/cli) |
| Claude desktop app | [Claude Desktop](https://www.anthropic.com/download) |
| Self-built page | Local page reading the three sources specified in the brief |

## Phase 2 — hard rejects first

Hard columns are the brief's lines H1–H8 in order: dead/sunsetting, cannot
run here, only its own agent, no 4–5-repo view, unsafe removal, not scriptable,
no live rail, cannot answer a rail prompt. `PASS*` is a design conclusion,
not a shipping-product claim. Scored columns: `C` concurrent grouping, `W`
launch worktree, `B` batch review, `T` external tickets, `L` truthful
liveness, `S` settings/hooks side effects, `D` file/diff, `N` waiting notice,
`O` one window, `$` cost, `M` maintenance. `Y` is supported; `N` is absent;
`?` is unverified. A hard fail stops the row, as required.

| Candidate / pinned version | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 | C | W | B | T | L | S | D | N | O | $ | M | Maintenance signal / verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Orca 1.4.197 | P | P | P | P | ? | P | P | P | N | ? | ? | ? | ? | ? | Y | Y | Y | Y | paid | vendor product | **Baseline**; claims retained from brief only |
| VS Code + Claude Code 2.1.269 | P | P | P | P | ? | **F H6** | P† | P† | Y | Y† | ? | ? | ? | ? | Y | ? | Y | mixed | vendor extension | The locally installed 2.1.269 manifest at `/home/caneff/.vscode-server/extensions/anthropic.claude-code-2.1.269-linux-x64/package.json` contributes the gated `claudeVSCodeSessionsList` webview, session-group and unread commands, `createWorktree`, terminal opening, and proposed-diff accept/reject. It clears H7/H8 on the feature evidence, but fails strict H6: the `code` CLI has no documented way to invoke these extension commands. |
| Zed `d27fa556ce1e` | P | P | P | P | ? | P | **F H7** | — | — | — | — | — | — | — | — | — | — | — | free | active company repo | Agent panel is per workspace; no documented 4–5-repo status rail ([source](https://github.com/zed-industries/zed/tree/d27fa556ce1e5aa9b606357b89a0841c9752f5ab)); reject H7 |
| Cursor / Windsurf / Trae / Kiro / Antigravity / Cline / Roo / Continue / PearAI / Void / JetBrains+Junie | P | P | **F H3** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | mixed | active products/repos | First-party material describes each vendor/extension agent; no source establishes launch/control of both chosen external CLIs. Reject H3, not an inference that terminals are absent. |
| Claude Desktop | P | P | **F H3** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | paid | active vendor app | Product is Claude's desktop client, not a host for arbitrary local Claude Code and Codex CLI sessions; reject H3 ([download](https://www.anthropic.com/download)). |
| Conductor / Nimbalyst (Crystal) / Sculptor / Daintree / HyprDesk / ai-14all / VibeTree / Arbor / Braid / cc-haha / Code-Bar / Tidebreak / Coppice / Xuanpu / Klaussy / Topics / Astera / Vibe Manager / Claude Orchestrator Desktop / Sequoias / Dashpod / Herd / Ziro / both Maestros / Conductor-arch / Yolium / Patchyard / Agent Tarn / Crowbar / TeamCow / both Arbor / Kine / Coding Canvas / Polaris / AI Sidekicks / NexusOps / Grove / DESK / Mozzie / Universal Agent Manager / SigmaLink / Codex Fleet / Jig / DSH / Swarm / Vicoa | **F H1** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | Owner repos discovered in the sweep are prototypes/one-person projects or lack a verified stable release and support signal. Per H1's cheap first test, they are not suitable production successors without an explicit maintenance commitment. |
| `work` CLI `a57b90871d6a` | P | **F H2** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | Owner README specifies Homebrew cask/macOS ([pinned README](https://github.com/tSquaredd/work-cli/blob/a57b90871d6a3852dad4caeb8e23c392593c618d/README.md)); reject H2 |
| MultiClaude 3.4.4 `984cdfe85eb3` | P | P | **F H3** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | free | recent July commit | README says it runs Claude Code in parallel; no Codex host path is documented ([pinned README](https://github.com/nguyennguyenit/MultiClaude/blob/984cdfe85eb3652295291bdf8ca4b4a69f4c3440/README.md)); reject H3 |
| Penguin Office `0a28d9b620ca` | **F H1** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | Last owner commit 2026-03-14 and a single-repo prototype; reject H1 ([pinned README](https://github.com/lalomorales22/penguin-office/blob/0a28d9b620ca6c08bf40a58441c35eae91b018ac/README.md)). |
| SquadFlow `57d2466b2e87` | P | **F H2** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | README says current release is Apple-Silicon macOS only ([pinned README](https://github.com/QuorraChord-A/SqualFlow/blob/57d2466b2e8755011a65f3002afc6e68c239bd4e/README.en.md)); reject H2 |
| SourceForge `0f384f2b7dba` | P | P | P | P | ? | **F H6** | — | — | — | — | — | — | — | — | — | — | — | — | free/alpha | latest owner commit July; alpha | Its README documents a GUI runner for Claude Code and Codex, but no public shell API for its lifecycle actions ([pinned README](https://github.com/trac41799/source-forge/blob/0f384f2b7dbabba10d76b487d70dfc4cf9b46473/README.md)); strict reject H6 |
| Claude Agent Teams / Claude Squad / dmux / Gas Town / OpenOrchestrator / ateam / opentree / shep-ai CLI | P | P | P | P | ? | P | **F H7** | — | — | — | — | — | — | — | — | — | — | — | free | active mixed | These are shell/TUI orchestration tools, not a one-window live rail that opens a waiting session. Gas Town's owner README documents persistent CLI orchestration, not that GUI requirement ([pinned README](https://github.com/gastownhall/gastown/blob/649b832b7672bc7a2dbef26f5983aba6198b819b/README.md)); reject H7. Claude Squad is also configuration, not a front end. |
| Self-built registry/worktree/tracker page (proposed) | P | P | P | P | P | P | P | P | Y | Y | Y | Y | Y | Y | Y | Y | Y | free | **high** | **Only conditional survivor.** Build precisely to the brief; no existing release to pin. |

### Survivor: self-built local page

The local page is the only survivor because it can deliberately make the
brief's existing session JSON the liveness authority, present a rail grouped
by repository and ticket, open the owning terminal to answer a prompt, and
invoke the existing shell dispatcher for every state-changing action. It
therefore avoids inventing a second agent protocol and does not need to write
`~/.claude/settings.json` or install hooks. Its serious downside is explicit:
Chris owns the glue, Windows/WSL boundary behavior, and compatibility tests.
This is a design score, not evidence that such a page already exists.

### Baseline: Orca

Orca remains the comparison row at the brief-pinned 1.4.197. I have not
assigned undocumented details a positive score: the brief establishes its rail,
terminals, file/diff, embedded browser and one-window workflow, but not its
worker grouping, launch-time worktree creation, batch-review policy, liveness
source, or removal confirmation. Those cells are intentionally `?` rather than
manufactured evidence.

### Re-assessment: VS Code + Claude Code 2.1.269

This row is **not a survivor**: its governing failure is hard reject **H6,
“Not scriptable.”** The [VS Code CLI documentation](https://code.visualstudio.com/docs/configure/command-line)
documents launching/reusing windows, opening folders and files, and opening a
file diff (and VS Code chat), but does not document executing a contributed
extension command. The local manifest instead exposes the needed Claude
actions only as VS Code commands—such as `claude-vscode.createWorktree`,
`claude-vscode.addSessionTabToGroup`, and
`claude-vscode.acceptProposedDiff`—so a shell dispatcher cannot reach every
action required by H6. Opening an existing file or `--diff` through `code` is
not a substitute for invoking those commands.

H4 is a pass for Chris’s stated setup: his `~/src/uberworkspace.code-workspace`
places all of the repositories in one multi-root window. VS Code documents a
multi-root workspace as multiple root folders with UI that identifies folders
and offers an overview of multiple active source-control repositories
([multi-root workspaces](https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces)).
That satisfies “4–5 repos in one view”; it does **not** prove that the Claude
session list groups or labels sessions by repository.

The manifest overturns the former H7 rejection: it contributes the
`claude-sessions-sidebar` view container and its `claudeVSCodeSessionsList`
webview, plus commands to reopen a closed session and focus the conversation.
Those are sufficient evidence against “No rail” and “Cannot open a session to
answer a prompt” (H7/H8). It also supports `C=Y` (add a session tab to a
group), `W=Y†` (the contributed Create Worktree action), and `D=Y` (proposed
diff accept/reject). `†` means the view and worktree command are each guarded
by a context key: `claude-vscode.sessionsListEnabled` and
`claude-vscode.createWorktreeEnabled`. The manifest does not establish that
either is enabled by default. `markSessionUnread` supports an unread marker,
but not an automatic waiting-state notification, so `N` remains unverified.
It likewise does not establish batch review, external-ticket integration,
truthful liveness, or settings/hooks side effects.

## Ranked recommendation

1. **Build the self-built local page (rank 1, conditional).** It beats Orca on
   the scored **truthful-liveness** line (read the actual session registry or
   process state, not terminal pixels), the **settings/hooks** line (zero,
   permanently), the **cost** line (no new subscription), and can be designed
   to group concurrent workers under a ticket. It is not a drop-in product;
   the high maintenance line is the price.
2. **Keep Orca 1.4.197 temporarily (rank 2, baseline).** It is the only
   verified ready product in this pass with the required rail and prompt-open
   behavior, but does not resolve the removal motivation recorded in the brief.
3. **VS Code + Claude Code 2.1.269 (rank 3, watch only).** The installed
   manifest now makes it the strongest off-the-shelf near-match: sessions rail,
   groups, worktree command, terminal opening, and proposed-diff decisions.
   It still fails exact hard-reject **H6: “Not scriptable”** because the
   documented `code` CLI cannot invoke its contributed Claude commands, so it
   is not admissible unless a supported shell/API surface is documented.
4. **SourceForge (rank 4, watch only).** It remains a closer external
   prototype than the broad rejected field, but likewise fails H6 for lack of
   a documented stable lifecycle CLI/API.

I did not trial-run the two prospective leaders: the self-built page does not
yet exist, and SourceForge would require installation. Opening VS Code or a
desktop app was also forbidden by the task. A no-install, under-one-hour trial
of SourceForge (or a minimal page proof) is the next step once permitted.

## Unverified claims

- Orca's workspace-removal confirmation behavior and all `?` baseline cells.
- Whether SourceForge works correctly through Windows 11 ↔ WSL2 in this exact
  NAT/interop setup; its source advertises platforms but this pass did not run it.
- Whether `claude-vscode.sessionsListEnabled` or
  `claude-vscode.createWorktreeEnabled` is enabled by default, whether the
  sessions list is repository-aware across Chris’s multi-root workspace, and
  whether its unread marker is set automatically when an agent waits. The
  installed manifest does not say.
- Whether Claude Code 2.1.269 has any supported shell/API bridge for the
  contributed VS Code commands. The documented `code` CLI does not show one.
- Whether any H1 prototype has a paid/support roadmap not stated in its owner
  repository, and whether the other grouped editor products have subsequently
  added a documented external-CLI fleet rail.
- All self-built-page scores are implementation requirements, not measurements.
