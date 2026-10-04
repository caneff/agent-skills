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
- Before every launch on this box, check `uptime` and `free -g`. Background
  runs share one 32-core, 39 GB WSL box with other agents; count every
  working Claude session against a 28-session cap, sessions you did not
  start included (idle and done do not count — the cap protects cores).
  burndown's counter is the reference: herdr's working panes plus every
  `claude` pid no pane resolves to; without herdr, `ps -eo comm= | grep -cx
  claude` (`ps aux | grep -c '[c]laude'` over-counts more than 2×). Keep the
  sum of per-process `ulimit -v` caps under about 24 GB. A brief that asks an
  agent to run solves, builds or test gates states the worker count and a
  wall-clock ceiling. Why: three reviewers each defaulting to 8 workers is
  24 cores for one diff, and caps summing to 66 GB crashed WSL.
- One file has one writer per run. With two workers live on one repo the
  controller names who owns each file; a change inside another worker's
  file reaches you as verbatim text the controller hands you to paste, or
  waits for that worker's PR — never as your own edit. Why: two writers on
  one file is a conflict nobody owns.
- Commit working code as soon as it runs and before launching a long job,
  staging only your own files. Why: another agent may be committing to the
  same branch.

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
- A subagent or teammate sends its final report with `SendMessage` to the
  agent that sent the brief, by that agent's name, as the last act of its
  turn — never to team-lead or main by default. If that agent has exited,
  send it to the controller, naming in the first line whose work it is and
  that the spawner was gone. Why: a report is never dropped because its
  addressee died.
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
  landing it there before removing the dead copy and holding one adoption
  lock (`~/.claude/sessions/.adopt.lock`) from its scan to its landing, so
  of two sessions adopting one worker exactly one wins, a crash mid-adopt
  leaves a duplicate the live copy outranks (never offered, never adopted)
  rather than a lost worker, and a later `/clear` here restores it like a
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
- A worker that stops without reporting must still wake the controller. Why:
  in the #781 trial two workers finished without reporting and the run
  stalled ~4 h unseen (#820). The controller subscribes to each worker it
  dispatches, and again after every message it sends one: `SendMessage` to
  the worker with `notify_when_idle: true` (no message needed). The idle
  notice reaches the controller only. On it, read that worker's pane
  (`herdr agent read <name>`) and say nothing to Chris unless the pane holds
  a question for him. The `Stop` hook `worker-stop-alert.sh` used to do this
  job by typing a line into the controller's herdr pane. It was unregistered
  from `settings.json` on 2026-10-04 because it typed into Chris's own input
  and fired about a dozen times in one burn without once being right. The script
  stays installed, and re-adding its `Stop` entry restores it.
- Long-running job: run it under `job-run --name <n> -- <cmd>` — output and
  exit survive a kill, and `job-run --status <n>` answers alive / finished /
  killed. Why: a plain background run loses its output and exit code when
  its shell is killed.
- Append a completion line to a progress file (e.g. `PROGRESS.md`) after
  every step and read it on wake; never stage or commit it. A background
  job's completion wakes the parent: end the turn, never block on it or poll
  in-turn (ruled 2026-10-04, superseding the block-in-turn step written for
  lost monitor notifications; #925's 180 `echo ok` calls was the cost). If a
  notification is lost, the next real event — a message, the progress file
  on wake — catches it. Why: a spin is invisible; every liveness signal reads
  healthy while it burns.
- A watch on a background job matches failure signatures
  (`Traceback|Error|REJECTED|bad_alloc|Killed`) and process exit, not only
  the success line — and never a per-item line inside a sweep. Report a
  crash, zero yield, UNKNOWN or failed verification to Chris before another
  attempt; never retry the same configuration silently. Why: a per-item
  match fires on the first item and reads as finishing; a success-only
  watch sleeps through a crash.
- A message that arrives while work is running changes that work. Check
  messages on every poll. If it changes a run's parameters, kill the run
  and restart with the new ones; if it adds to a deliverable, fold it in
  and grep the deliverable for it before reporting done. Why: a message
  read after the run is a run done twice.
- Scripts, logs and outputs of long runs go in a git-ignored scratch
  directory inside the worktree or the repo's research directory — never
  `/tmp` or the session scratchpad, which a WSL restart wipes. Parallel
  workers each get their own filename there. Why: a name unique only inside
  one session scratchpad is not unique. (Retires when #1234's hook lands.)
- A long unattended fetch or search writes each result to disk as it lands
  and skips what is already there on restart. Why: a crash then costs one
  item rather than the run.
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
