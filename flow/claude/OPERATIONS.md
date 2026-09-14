# Operations detail (read when dispatching agents, running long jobs, or merging)

Pointer target for `CLAUDE.md` § Agents and jobs. One lane: dispatch, control,
wait, status, end. Terms as `~/.agents/skills/CONTEXT.md` defines them.

## Dispatch

- A ticket becomes a worker through `implement-dispatch <n> [--model
  sonnet|opus]`, run by the dispatcher on the primary checkout's default
  branch; `implement/SKILL.md` § Dispatch. It claims, creates the workspace,
  starts the worker in a herdr pane, and puts the tier and the controller's
  session name in the brief. Why: a claim made from inside the workspace let
  two sessions dispatch the same ticket, and a brief sent before the trust
  dialog is accepted lands in the dialog.
- Every Agent call passes `model` — a bare call inherits the session's model.
  Explore/lookup → `sonnet`, review/diagnosis → `opus`. Rubric:
  `~/.agents/skills/flow/claude/subagent-tiers.md`. Why: a bare call runs a
  lookup on the session's own, most expensive model.
- Never add `--dangerously-skip-permissions` (or any flag) to an agent
  launch. Why: the permission prompt is the only stop between an agent and an
  irreversible command.
- A worker verifies `pwd` and `git branch --show-current` against its own
  workspace before every commit and before any long run. A subagent in a
  shared session never calls EnterWorktree: the pin is session-wide and
  re-pins everyone. Create with `git worktree add`, work via absolute paths
  and `git -C`, pass `--repo` to every `gh` call. Why: an EnterWorktree that
  lands in a path that already exists is someone else's tree, and a commit
  made from the wrong cwd lands there.

### Herdr configuration

- Worktree path: `[worktrees]` `directory = ".claude/worktrees"` in
  `~/.config/herdr/config.toml`, so a worktree opened through herdr lands at
  `<repo>/.claude/worktrees/<branch-slug>`, where `merge-cleanup` looks.
- `herdr-reviewr` is linked; the `herdr-push` plugin (`herdr.push`, feeds
  `herdr-remote`'s mobile approval relay) is installed pinned at `f4fdb06`
  (2026-09-13, #726) but inert: it exits unless `HERDR_RELAY` is set in its
  `.env`, and no relay is stood up. Reinstalling or updating it needs my own
  hands (`--ref <sha> --yes`), since the auto-mode classifier denies it as
  untrusted code integration.
- **The herdr `claude` integration stays installed** (`herdr integration
  status` shows `claude: current`). Screen detection gives idle/working/blocked
  for free, but not the session id: its SessionStart hook
  (`~/.claude/hooks/herdr-agent-state.sh`) is what reports each pane's Claude
  sessionId as `agent_session.value`, and `merge-cleanup`'s live-session guard
  matches a worker's own session against that value — without it, cleanup
  refuses an idle worker (#745). Never uninstall it; if a herdr update drops
  it, `herdr integration install claude` needs my own hands (the classifier
  denies it as self-modification). Ruled 2026-09-13, #725.
- **Wispr Flow in herdr needs a `shift+insert` paste binding in VS Code**:
  `{"key": "shift+insert", "command": "workbench.action.terminal.paste",
  "when": "terminalFocus"}` in the Windows user `keybindings.json`. Wispr
  pastes by simulating Shift+Insert. herdr requests Kitty keyboard flags 7
  (31 when a pane asks to report all keys), and with the protocol active VS
  Code encodes Shift+Insert as a key (`ESC[2;2~`) instead of pasting, so no
  text lands and Wispr reports no text box. The binding runs before the
  encoder; a raw-byte probe then shows a bracketed paste. Keep
  `terminal.integrated.enableKittyKeyboardProtocol` on — turning it off also
  fixes Wispr but makes Ctrl+Enter send the same bytes as Enter. Not the
  cause: `ui.host_cursor`, editor-vs-panel placement. Same class:
  earendil-works/pi#8778. Fixed 2026-09-14.

## Control

- The dispatching session is the worker's **controller**. The worker sends
  every question and its finish notice ("PR up", or the landed sha on the
  light tier) to the controller with `SendMessage`, never to me. On my
  repos the controller then merges (`implement/SKILL.md` § The merge) —
  except on a `ready-for-human` ticket, whose merge line comes to me. Why:
  I marked that work for my own hands, so I see it before it lands.
- What the controller rules on and escalates to me: its entry in
  `~/.agents/skills/CONTEXT.md`. Why: each escalation listed there is an
  outcome a controller cannot undo on my behalf.
- **Relay the delta, not the report.** When a worker or subagent finishes,
  say only what it added; if it confirms what I already said, that is one
  sentence. Never answer a question and delegate the same question. An idle
  notice that repeats a report already relayed gets no reply at all. Why: a
  repeated report costs me a read and carries nothing new.

## Wait

- The controller never polls a worker. Its wait is going idle: a worker's
  `SendMessage` wakes an idle controller as its next turn about a second
  after the send. While the controller is inside a tool call the message is
  held, unseen, until that call returns, so it never sits in a long tool
  call (an untimed `herdr agent wait`, a long sleep, a blocking
  `TaskOutput`) while workers are out. To hear when a session goes idle,
  send it `SendMessage` with `notify_when_idle: true`. Why: polling loops
  and "are you done?" messages cost turns and interrupt the worker; measured
  on the socket fan-in prototype (#778).
- Long-running job: run it under `job-run --name <n> -- <cmd>` — output and
  exit survive a kill, and `job-run --status <n>` answers alive / finished /
  killed. Why: a plain background run loses its output and exit code when
  its shell is killed.
- Append a completion line to a progress file (e.g. `PROGRESS.md`) after
  every step and read it on wake; never stage or commit it. Never go idle
  waiting on a background task: block on it (TaskOutput block=true, or poll
  in-turn) and finish the checklist in the same turn. Why: monitor
  notifications get lost, and an idle session is not woken by a lost one.
- A Monitor pattern matches only the final line, a timeout, or an error
  string — never a per-item line inside a sweep. Why: a per-item match fires
  on the first item and reads as the run finishing.
- No PushNotification toasts and no new desktop notifications; attention is
  batched. Why: each toast interrupts me for something not yet actionable.

## Status

- Status comes from the machine, never the terminal tail: `herdr agent get`,
  the sessions registry, HEAD, `ls-remote`, `gh pr list`. Detail:
  `~/.agents/skills/flow/claude/agent-status.md`. Why: a cached screen with
  unchanged text looks the same for a working worker and a dead one.
- When I ask "status" or "why is this taking so long", answer in three lines
  — what each worker is on, what blocks, and the cut line that ships now —
  from evidence just checked, never from what you told a worker to do. A
  second ask means the first answer had nothing in it. Cut scope and split
  the rest into follow-up tickets when I say cut, or when the honest status
  is that it is overrunning. Why: an answer built from what a worker was told
  restates the plan, not the state.

## End

- Before reporting a commit sha, `git status --porcelain` is empty, and fix
  commits stack instead of amending. Why: the report describes the commit,
  not the working tree, and an amend erases a sha already handed over.
- The review loop, the before-the-PR checks and the controller's merge
  (CLEAN, `Closes` verified): `implement/SKILL.md` § Heavy tier; the light
  tier's landing and its `Closes` check: § Light tier. Why: one home, so the
  lane and this file cannot drift apart.
- The controller follows every merge with
  `merge-cleanup --repo <primary checkout> <branch>`
  (`--help` for PR/URL and `--sweep`). The sweep shows its plan and asks
  before deleting; `--yes` answers for an unattended run. It removes the
  workspace, deletes the branch local and remote (the tip stays under
  `refs/deleted/<branch>`; `git branch <branch> refs/deleted/<branch>`
  restores it), closes the herdr workspace, and fast-forwards the primary
  checkout. Its live-session guard stops an idle worker's herdr agent itself
  and proceeds; a working or blocked agent, or a live session outside herdr,
  still refuses. Why: nothing else cleans up after a merge, worktrees pile
  up, and closing an idle worker's pane by hand was a chore Chris no longer
  does.
