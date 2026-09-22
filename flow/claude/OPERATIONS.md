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
  It also installs the commit-identity guard beside the repo's hooks and
  unconditionally makes `pre-commit` *and* `pre-push` its own wrapper: a
  foreign hook at either slot is never trusted by its text, only taken
  over — moved aside under a stable name (`pre-commit.foreign` /
  `pre-push.foreign`), forced executable, and run by the wrapper before the
  wrapper always runs the guard itself
  (`flow/lane/src/bin/implement_dispatch.rs`, `install_identity_guard`,
  #1009). `pre-commit` alone never fires on a rebase or cherry-pick that
  replays a commit under a different identity, so `pre-push` re-checks every
  commit about to be pushed against the same checkout-configured
  `user.email` and the same `COMMIT_IDENTITY_OVERRIDE` escape (#1006).
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
- **herdr's host is Zed's integrated terminal** (Windows Zed over its WSL
  remote, ruled 2026-09-17), in the same window as the file viewer
  (`zed <path>:<line>`, see `VISUAL-INSPECTION.md`). It needs no custom
  bindings: prefix keys, sidebar clicks, Shift+Enter, Wispr Flow dictation
  and Ctrl+V image paste into Claude Code were all checked working on Zed
  1.20.2. herdr takes one client at a time — attaching from another terminal
  drops the current one; the server and panes keep running, so re-running
  `herdr` is the whole recovery.
- **Zed's terminal attaches herdr by itself.** The hook is in `~/.bashrc`,
  right after the `herdr()` wrapper: `ZED_TERM` is set only in a Zed
  terminal, so an interactive login shell there runs `herdr && exit`. It is
  guarded on `HERDR_PANE_ID` (unset only outside a herdr pane -- without it
  the shells herdr starts in its own panes re-attach forever), on `$-`
  containing `i` (never an agent Bash tool), and on `HERDR_NO_AUTOATTACH=1`,
  which gets you a plain shell in Zed when you want one. `herdr && exit`
  rather than `exec`, so a failed attach leaves the error on a live shell.
  Zed's own `terminal.shell` setting is **not** the mechanism: it is ignored
  over the WSL remote, both in the Windows `settings.json` and in a project
  `.zed/settings.json` (checked 2026-09-20 on Zed 1.20.2 -- terminals still
  came up `/bin/bash -l`). `~/.bashrc` is in no git repo; the backup from
  this change is `~/.bashrc.bak-20260920-001302`.
- **Toast clicks follow the host.** `[ui.toast] delivery = "system"` calls
  `~/.local/bin/notify-send`, a shim that raises a Windows toast whose click
  runs `herdrfocus:<pane>` → `herdr-focus.vbs` → `herdr-focus-pick.ps1`
  (raises the host window by owning process) → `herdr-focus-latest` (focuses
  the pane). The picker's host list is `Zed,wezterm-gui,WindowsTerminal,Code`,
  first match wins; a host missing from it means a click raises nothing.
  The five live in `flow/bin/`; `flow/bin/herdr-toast-install` (run from the
  primary checkout) links them into `~/.local/bin` and points the
  `herdrfocus` registry handler at `flow/bin`. Windows cannot follow a WSL
  symlink over `\\wsl.localhost`, so the `.vbs` and `.ps1` are addressed by
  their `flow/bin` path, never the `~/.local/bin` link. Test with
  `HERDR_TOAST_PANE=<pane id> notify-send "t" "b"` from a different
  workspace — a toast for the already-focused pane looks like a no-op.
- **Fallback host: WezTerm nightly**, installed and configured
  (`C:\Users\canef\.wezterm.lua`). There Wispr pastes with Ctrl+V, so
  `CTRL+v`, `SHIFT+Insert` and a bare right click are bound to
  `PasteFrom 'Clipboard'`, and image paste is Alt+V (forwards the raw
  Ctrl+V). VS Code's terminal is retired as a host: it stopped delivering
  sidebar clicks, cause never found. The WezTerm install route, the paste
  probe, and the VS Code Shift+Insert diagnosis (2026-09-14) are in
  `docs/research/herdr-host-terminal-and-editor.md`.

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
- **The controller/worker pairing survives `/clear`** (#964). `/clear` wipes
  a session's context, not its process: the session's pid, and everything
  keyed to it, are still there afterward. `implement-dispatch` appends one
  record per worker it starts to `~/.claude/sessions/<pid>.workers.jsonl`,
  a sibling of that pid's own session registry file — `{agent, tickets,
  branch, workspace, repo, cleanup, chris_merges, dispatched_at,
  proc_start}`, `proc_start` being the controller session's own
  `/proc/<pid>/stat` starttime at dispatch time. A `SessionStart` hook,
  `controller-restore` (`flow/lane/src/bin/controller_restore.rs`, wired into
  `flow/claude/settings.json`'s `SessionStart` array), reads that file for
  the resuming session's own pid on every session start, `/clear` included,
  drops any record whose `proc_start` does not match the resuming session's
  own — pids are small and get reused, especially across a WSL restart, so a
  sidecar left behind by a dead controller must never restore into whatever
  unrelated session now holds that pid — asks `herdr agent list` which of
  the remaining workers' agents are still alive and `gh pr list --head
  <branch>` whether each has an open or merged PR, and prints one line per
  worker: `You control implement-143 (sudokupad-art-143, agent working): PR
  #152 open, not merged — follow implement/SKILL.md § The merge; cleanup:
  <line>`. Both queries share one 12s deadline (under the hook's own 15s
  timeout in `settings.json`), so a worker whose query never got its turn is
  printed `unchecked` rather than silently dropped or misread as `herdr`/`gh`
  having failed. It is read-only besides that record file — `append` and
  `merge-cleanup`'s own removal take the same exclusive file lock on the
  sidecar, so the two can never interleave and lose a record — never
  re-sends a brief, and re-arms nothing: the printed line is the whole
  recovery; act on it the same as any other worker report. A session that
  has dispatched nothing, or whose every record is stale, gets no worker
  lines. `merge-cleanup` removes a worker's record when it removes that
  worker's workspace, so a landed and cleaned-up branch has nothing left to
  restore.
- **A dead controller's workers can be adopted** (#1098). A controller
  whose process exits — not a `/clear` — leaves its workers with no one to
  report to and no one allowed to merge their PRs, and `controller-restore`
  restores only into the same process. On every session start it also
  prints one line per orphan: a record whose controller's pid is dead, or
  alive under another starttime (a reused pid), whose workspace still
  exists and sits strictly under the session's cwd, so a worker's own
  session is never offered itself — `Orphaned worker implement-345
  (twitch-rules-scroller-345): its controller, pid 7313, is gone — adopt it
  with: controller-adopt twitch-rules-scroller-345`. It prints only.
  `controller-adopt <agent>`, run from the primary checkout, moves that
  record into this session's own `<pid>.workers.jsonl` under its starttime,
  holding the sidecar lock on both files, so of two sessions adopting one
  worker exactly one wins and a later `/clear` here restores it like a
  dispatched worker. It refuses while the worker's controller is alive, when
  the workspace is gone, off the primary checkout, and — before moving
  anything — when `herdr agent list` cannot answer, since the name it
  re-points the worker at would then be a guess. A second run on a worker
  this session already adopted says so and succeeds. It prints `Your
  controller is now <name>` — this session's herdr agent name, else its
  session name — for you to `SendMessage` to the worker; that message
  replaces the brief's controller (`implement/SKILL.md` § Control). Then the
  worker is yours, merge included. A burn has its own path, `runfile.py
  resume`.

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
- A worker that stops without a successful `SendMessage` to its controller
  since its last prompt still wakes the controller — unless it is waiting
  (a subagent, a background shell or a Monitor task still out) or it
  already reported and has done nothing since (#886): the `Stop` hook
  `worker-stop-alert.sh` types one line into the controller's herdr pane,
  `[worker-stop-alert] worker #<n> stopped without reporting to
  <controller> (herdr agent <name>)`. Read that agent's
  pane (`herdr agent read <name>`) for the report it never sent. herdr
  refuses a prompt to a blocked pane; the hook retries with backoff for up to
  12 s, then writes a `not-sent` line (`controller blocked: …`) to
  `~/.claude/worker-stop-alerts.log`. So while workers are out, read the
  `not-sent` lines added to that log since your last read, on every wake and
  before ending a turn — the one read the rule above allows. Why: in the
  #781 trial two workers finished without reporting and the run stalled ~4 h
  unseen (#820).
- A worker that never stops raises no stop alert, and its transcript mtime
  and `working` state read healthy while it spins. The `PostToolUse` hook
  `worker-spin-alert.sh` runs inside the turn: the same tool with
  byte-identical input 20 times in a row (no other call between) types
  `[worker-spin-alert] worker #<n> repeated <tool> <input> at least <k>
  times in a row` into your pane, once per run, logged to
  `~/.claude/worker-spin-alerts.log`. To check a transcript on demand:
  `bash ~/.claude/hooks/worker-spin-alert.sh --classify <transcript.jsonl>`.
  Why: a worker made 180 `echo ok` calls waiting on a subagent (#925).
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
  tier's landing and its `Closes` check: `implement/SKILL.md` § Light tier. Why: one home, so the
  lane and this file cannot drift apart.
- The controller follows every merge with
  `merge-cleanup --repo <primary checkout> <branch>`
  (`--help` for PR/URL, `--sweep` and `--reap`). The sweep shows its plan and asks
  before deleting; `--yes` answers for an unattended run. It removes the
  workspace, deletes the branch local and remote (the tip stays under
  `refs/deleted/<branch>`; `git branch <branch> refs/deleted/<branch>`
  restores it), closes the herdr workspace, and fast-forwards the primary
  checkout. Its live-session guard stops an idle worker's herdr agent itself
  and proceeds; a working or blocked agent, or a live session outside herdr,
  still refuses. Why: nothing else cleans up after a merge, worktrees pile
  up, and closing an idle worker's pane by hand was a chore Chris no longer
  does.
- A controller that died mid-run never makes that call, so its worker's
  workspace is stranded. `merge-cleanup --reap --repo <primary checkout>`
  lists that one repo's `implement-*` workspaces with a disposition each and
  removes nothing; `--yes` then tears down the landed, clean, dead ones
  through the same single-branch path. It has no `--discard` and no
  `--force`: a workspace holding work, a live session, or an unmerged branch
  is named and skipped. Why: nothing else reaps after a dead controller, and
  a reaper that could override a guard would be a sweep.
