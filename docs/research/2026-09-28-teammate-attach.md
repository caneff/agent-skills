# Entering a teammate, handing it an image, and the "CLAUDE.md missing" report (2026-10-04)

Question (#1232): how does Chris view and type into a named teammate or
subagent, how does he hand it an image, and which case is a session that
reported `CLAUDE.md` missing?

Every claim below is marked **stated** (the page says it; quoted where a
quotation marks follow, otherwise a close paraphrase), **inferred** (ours, from
stated facts), **checked** (read from this repo or box on the date given) or
**tried live** (run on the date given, result stated). Pages were fetched in
full on 2026-10-04 against Claude Code 2.1.289; the ticket's preliminary
pointers were checked against them, not trusted.

## Answer

1. **Enter a teammate: the agent panel under the prompt input.** Up/Down
   selects a row, Enter opens its transcript, and typing there messages it.
   `claude agents` does **not** list teammates or subagents.
2. **Hand it an image: save the file under a stable path and message the
   path.** The teammate opens it with `Read`. Tried live: works. Pasting
   while viewing the teammate is untested here and undocumented for teammates.
3. **"CLAUDE.md missing": a teammate loads it, so the report fits an Explore
   or Plan subagent, or a custom agent with `omitClaudeMd: true`.** Which one
   the 2026-09-28 session was is not recoverable from the ticket.

## 1. Viewing and typing into a teammate

Source: "Orchestrate teams of Claude Code sessions",
https://code.claude.com/docs/en/agent-teams.md

- Stated: "The lead's terminal lists teammates in the agent panel below the
  prompt input. From the panel: **Up and down arrows**: select a teammate;
  **Enter**: open the selected teammate's transcript and message it directly;
  **Escape**: clear the selection. While you're viewing a teammate's
  transcript, Escape interrupts that teammate's current turn."
- Stated: the default is `"in-process"`: "all teammates run inside your main
  terminal ... Works in any terminal, no extra setup required." Split panes
  "Requires tmux, or iTerm2", and "isn't supported in VS Code's integrated
  terminal, Windows Terminal, or Ghostty."
- Stated: an idle row stays while any agent is working; once all are idle,
  rows hide after 30 seconds and "reappear on the teammate's next turn; the
  teammate stays running and addressable while hidden". More than three idle
  rows collapse into `N idle agents`; Enter expands. A hidden teammate is
  brought back by sending it a message by name.
- Stated: "Press `x` on a selected teammate to stop it."
- Stated: while viewing an in-process teammate, plain text and skills go to
  it; built-in commands go to the lead. `/compact`, `/clear`, `/rewind` ask
  for confirmation; `/model` and `/fast` do not run from that view.
- Stated: in-process teammates are not restored by `/resume` or `/rewind`.

Source: "Create custom subagents",
https://code.claude.com/docs/en/sub-agents.md

- Stated: "While that subagent's row is still in the subagent panel, type into
  its transcript to resume it yourself."
- Stated: with agent teams enabled, "a subagent that Claude spawns from the
  main conversation with a `name` launches as a teammate instead", unless it
  is a fork or passes `isolation`.

Source: "Manage multiple agents with agent view",
https://code.claude.com/docs/en/agent-view.md

- Stated: `claude agents` lists background sessions; Enter or → attaches, ←
  on an empty prompt detaches.
- Stated: "[Subagents] and [teammates] a session spawns aren't listed as
  separate rows." So this page does **not** apply to a teammate. The ticket's
  preliminary pointer to it was wrong for this question.

**Inside a herdr pane** (inferred): herdr's pane is an ordinary terminal
running the lead's `claude`, so the in-process panel is the route. The
managed `settings.json` sets `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and no
`teammateMode`, so the default `in-process` holds. Split-pane mode would need
tmux inside the pane; not set up, and out of scope here. Why a teammate was
"hard to find": the row hides 30 seconds after the panel goes idle, and
because `agent teams` is on, any subagent the lead names becomes a teammate (a fork, or a call passing
`isolation`, does not)
whether or not Chris asked for one.

**Spawning one he can enter** (inferred from the above and
`flow/claude/subagent-tiers.md`): the lead calls Agent with a `name` and
`run_in_background: true`. That makes a persistent teammate that parks idle,
and a name Chris can also use in the lead's prompt ("message `<name>`").
Telling the lead the name at spawn gives a predictable one; the page says
"tell the lead what to call each teammate in your spawn instruction."

## 2. Handing a teammate an image

Source: "Interactive mode",
https://code.claude.com/docs/en/interactive-mode.md

- Stated: "`Ctrl+V` or `Cmd+V` (iTerm2) or `Alt+V` (Windows and WSL) | Paste
  image from clipboard | Inserts an `[Image #N]` chip at the cursor ... On
  WSL, both `Ctrl+V` and `Alt+V` are bound; use `Alt+V` if your terminal
  intercepts `Ctrl+V`."
- Not documented: whether a paste made while viewing an in-process teammate's
  transcript reaches that teammate. The agent-teams, sub-agents and
  interactive-mode pages were all opened; none has a teammate image example.
  The 2026-10-02 retro reports four failed pastes into a subagent Chris
  entered (the lead then saved the clipboard to a file). That is the only
  evidence, and it points to "does not work"; it is a report, not a repro.
- Route A, paste while viewing the teammate: **untested** here (an
  interactive TTY is needed; this run had none).
- Route B, save a file and message the path: **tried live 2026-10-04,
  worked.** A named background teammate (`probe-teammate`, haiku,
  `status: teammate_spawned`) was sent an absolute path to a 64x64 red PNG
  and replied "red PROBE-OK" after opening it with `Read`.

**Recommendation: route B.** It needs no terminal support, works for any
teammate, and does not depend on which transcript has focus. The clipboard
half is one command, in `VISUAL-INSPECTION.md` § Getting a pasted image to an
agent as a file. Stable path = a git-ignored directory outside
`.claude/worktrees`, such as the primary checkout's `.scratch/`.

## 3. The "CLAUDE.md missing" report

Sources: agent-teams.md and sub-agents.md, as above.

- Stated (agent-teams.md): "When spawned, a teammate loads the same project
  context as a regular session: CLAUDE.md, MCP servers, and skills."
- Stated (sub-agents.md): "Explore and Plan skip your CLAUDE.md files and the
  git status snapshot to keep research fast and inexpensive. Every other
  built-in and custom subagent loads both, unless its definition sets the
  `omitClaudeMd` field."
- Stated: a fork "sees the same system prompt, tools, model, and message
  history as the main session", so it has CLAUDE.md too.
- Stated: `--setting-sources` on the lead restricts a teammate's sources the
  same way.
- Checked 2026-10-04: `~/.claude/CLAUDE.md` is a symlink to
  `~/.agents/skills/flow/claude/CLAUDE.md` (made by `flow/install.sh` line
  37) and resolves. No file in `flow/claude/agents/` sets `omitClaudeMd`.

Which case fits (inferred): a teammate (or a fork) loads CLAUDE.md, so a
teammate that said it was missing is not explained by a documented skip. The
two documented skips are an **Explore or Plan subagent**, which is the likely
one because those are the types the lead reaches for in a fan-out, or a
custom agent with `omitClaudeMd`. A dangling symlink is a third candidate:
the user-path-rules probe (`2026-10-04-user-path-rules-probe.md`) saw a
dangling symlinked *rule* file ignored, but nobody has tested a dangling
`CLAUDE.md`, so that is a guess. The session itself is gone; the ticket does
not say its type. To tell next time, ask the session what its agent type is
and read `~/.claude/teams/session-*/config.json` `members[].agentType`.

## Not covered

No claim about a teammate's own `/memory` or `/status` output was tested.
