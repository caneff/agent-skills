# Front end after Orca: requirements and research brief

Date: 2026-09-12. Settled by grilling on wayfinder map
[Orca exit](https://github.com/caneff/agent-skills/issues/700), ticket
[The front end after Orca](https://github.com/caneff/agent-skills/issues/704).
Two researchers score candidates independently against this brief; neither
sees the other's list before reporting. Scope: the front end for all agent
work, not only the one-ticket case.

## The question

Chris runs agents across 4-5 repos: today one ticket per worktree per agent
session, with Chris merging each PR; next, several workers on one spec at
once, and Codex CLI alongside Claude Code. The front end is the window for
all of that, so it is scored for all of it. Orca 1.4.197 is the current front end: a rail with one
row per worktree across 4-5 repos, a terminal per agent, file open and diff,
an embedded browser. Orca is being removed for the cost it imposed
(see [#692](https://github.com/caneff/agent-skills/issues/692)). What replaces
the window Chris watches and clicks in?

## Environment

- Desktop: Windows 11 build 26200.9445. Shell: WSL2 Ubuntu 24.04, NAT
  networking, interop enabled.
- **A Windows-native app that opens WSL terminals is preferred** over
  something that runs inside Linux. Either is admissible.
- Claude Code CLI 2.1.269, VS Code 1.137.0 with `anthropic.claude-code`
  2.1.269, one multi-root workspace holding every repo
  (`~/src/uberworkspace.code-workspace`).
- Worktrees will live at `<repo>/.claude/worktrees/<name>`; the agent
  creates them and dispatches the worker from a shell.
- Every live session writes `~/.claude/sessions/<pid>.json` (cwd, status,
  liveness); transcripts live under `~/.claude/projects/<encoded-cwd>/`.

## Hard rejects, cheapest first

1. **Dead or sunsetting.** No release or commit in months, single maintainer
   gone quiet, sunset notice. Check first, drop fast.
2. **Cannot run here.** Neither a Linux/WSL2 binary nor a Windows app that
   reaches WSL.
3. **Brings only its own agent.** It must run the CLIs Chris chooses, Claude
   Code today and Codex CLI next. Running its own agent *in addition* is fine.
4. **Cannot show 4-5 repos in one view**, or switch between running agents
   without one window per repo.
5. **Not scriptable.** Every action `/implement` needs must be reachable from
   a shell, so dispatch stays unattended.
6. **No rail.** Cannot show in-flight work across repos with a live status.
7. **Cannot open a session to answer a prompt** from that rail.

## Scored

- Removes a workspace holding a live session without refusing or confirming.
  *Demoted from hard reject on 2026-09-12 (Chris, after the herdr trial): the
  lane never calls the front end's remove; `merge-cleanup` gains a check that
  refuses to remove a worktree with a live session in `~/.claude/sessions/`,
  which holds under any front end.*
- Many concurrent sessions in one repo, grouped so several workers on one
  spec read as one unit, and any one of them can be opened.
- Workspace per ticket made at launch, not part-way through.
- Batch review: many PRs reviewable in one sitting; no mandatory per-ticket
  interactive gate.
- Tickets authored elsewhere (GitHub issues, from wayfinder).
- Truthful liveness: status from the session registry or process state, not
  a cached terminal screen.
- Writes to `~/.claude/settings.json` or installs hooks: penalised, more so
  if it cannot be opted out of permanently.
- File open and diff from the rail.
- Notification when an agent is waiting on Chris.
- One window, not one per worktree.
- Cost: paid tools are in, scored.
- Maintenance cost Chris carries (glue scripts, wrappers, workarounds).

## Recorded, unscored

Keyboard-only navigation between sessions; survives a VS Code or Windows
restart with sessions intact; what deletes a workspace, on what signal;
whether landing straight onto `main` with no PR remains possible.

## Candidate classes, all swept

1. Editors with agent panels: VS Code + Claude Code extension, Cursor, Zed,
   JetBrains, Windsurf.
2. Orchestrator desktop apps: Orca (baseline row, 1.4.197), Conductor,
   Nimbalyst, Sculptor, Crystal, and kin.
3. Terminal tools: `claude agents`, Claude Squad, dmux, Gas Town, and kin.
4. The Claude desktop app.
5. A self-built local page reading the session registry, `git worktree list`
   per repo, and the tracker, with an honest maintenance-cost line.

Orca is scored as the baseline so the winner beats it on named lines.

## Evidence standard

From [#488](https://github.com/caneff/agent-skills/issues/488): pinned version
or commit, every fact from the tool's own docs or source, hard rejects stated
with the line that killed them, maintenance signal from the repo itself. Two
phases, not merged: find names, then score survivors. Trial-run the top two
where a trial costs under an hour and installs nothing permanent.
