# Operations detail (read when dispatching agents, running long jobs, or merging)

Pointer target for `CLAUDE.md` § Agents and jobs. Orca-specific lines are
tagged **[Orca]** and go with the Orca exit (see
`docs/research/2026-09-10-orca-removal-dependency-inventory.md`).

## Dispatching an agent

- Every Agent call passes `model` — the session is Fable and a bare call
  inherits it. Explore/lookup → `sonnet`, review/diagnosis → `opus`. Rubric:
  `~/.agents/skills/flow/claude/subagent-tiers.md`.
- Never add `--dangerously-skip-permissions` (or any flag) to an agent
  launch; use my default agent args as configured.
- A worker verifies `pwd` and `git branch --show-current` against its own
  assigned worktree before every commit and before any long run; an
  EnterWorktree that lands in a path that already exists is someone else's
  tree — leave it. A subagent in a shared session never calls EnterWorktree
  at all: the pin is session-wide and re-pins everyone. Create with
  `git worktree add`, work via absolute paths and `git -C`, pass `--repo` to
  every `gh` call.
- **Delegated report contract**: the message to the coordinator leads with
  the verdict line and the sha, stays under ~300 words / 60 lines, and names
  the file holding the full text — messages truncate in transit. Put that
  delivery instruction in the spawn prompt itself ("send the report with
  SendMessage to main, verdict first, end with the SHA"). After sending, stay
  quiet until pinged — never resend — and answer every direct question in
  the coordinator's message before going idle. A coordinator that gets a
  cut-off report asks for the tail only. A research or survey delegate reads
  sequentially itself and never spawns sub-agents.
- **Relay the delta, not the report.** When a subagent finishes, say only
  what it added; if it confirms what I already said, that is one sentence.
  Never answer a question and delegate the same question — pick one. An idle
  notification that repeats a report already relayed gets no reply at all.

## Reading an agent's status

Status comes from the process table, never the terminal tail — a cached
screen with unchanged text is not evidence of work. Check children
(`ps --ppid`), HEAD, `ls-remote`, `gh pr list`. Detail:
`~/.agents/skills/flow/claude/agent-status.md`.

When I ask "status" or "why is this taking so long", answer in three lines —
what each worker is on, what blocks, and the cut line that ships now — from
evidence just checked (process table, progress file, git log, the artifact),
never from what you told a worker to do. A second ask means the first answer
had nothing in it; go get the real state and answer again. Cut scope and
split the rest into follow-up tickets when I say cut, or when the honest
status is that it is overrunning.

## Long-running jobs

- Run it under `job-run --name <n> -- <cmd>` — output and exit survive a
  kill, and `job-run --status <n>` answers alive / finished / killed.
  `job-run --help` for detail.
- Append a completion line to a progress file (e.g. `PROGRESS.md`) after
  every step and check that file on wake — monitor notifications get lost.
  The progress file is a working artifact: never stage or commit it. Never go
  idle waiting on a background task: block on it (TaskOutput block=true, or
  poll in-turn) and finish the whole checklist in the same turn. A delegated
  agent finishes by sending its final report; going idle is not a report.
- A Monitor pattern matches only the final line, a timeout, or an error
  string — never a per-item line such as `seed N done` or a per-fixture
  verdict inside a sweep.
- No PushNotification toasts and no new desktop notifications; attention is
  batched every N minutes, never per-event.
- **[Orca]** Never `ORCA terminal wait` — stale server-side waiters fail with
  `waiter_exists`. Use `orca-wait --terminal <handle> --for exit|tui-idle
  [--timeout-ms N]` (script in `~/.local/bin`; exit 0 = met, 2 = timeout).

## Committing, reviewing, merging

- Before reporting a commit sha, `git status --porcelain` is empty — the
  report describes the commit, not the working tree. While a branch is under
  review, stack fix commits instead of amending, so every reported sha
  survives.
- A branch with fix commits on top of the last reviewed sha is unreviewed;
  its PR body names that sha and says the commits after it were not
  re-reviewed. Whether a fresh review runs is the lane's rule:
  `implement/SKILL.md` § Finish caps it at three passes then park;
  `implement-spec` § Landing loops to the same cap; `burndown/SKILL.md`
  step 5 runs one round and no re-review. A failed mechanical gate (scope
  check, test seam, pre-report-gate.sh) is not a review pass; two of those on
  one ticket, then park.
- **The merge line** carries `--repo owner/name` and goes out only after
  `gh pr view --json isDraft,mergeStateStatus` shows not-draft and CLEAN.
  **[Orca]** Drop `--delete-branch` whenever an Orca worktree still holds the
  branch (fails with "'main' is already used by worktree") and pair the merge
  with `orca-ide worktree rm --worktree <full branch name>`.
- After a land or merge, check each `Closes` issue with
  `gh issue view --repo` before reporting it closed — a rebase can rewrite
  the commit so the trailer never fires.
- **[Orca]** Orca does not clean up after a merge — run
  `merge-cleanup --repo <primary checkout> <branch>` (`--help` for PR/URL and
  `--sweep`), or worktrees pile up.
- **[Orca]** Never bare `orca` on Linux — it is the GNOME screen reader and
  starts speech. Use `orca-ide`, or `$ORCA_CLI_COMMAND` where Orca exports it.
