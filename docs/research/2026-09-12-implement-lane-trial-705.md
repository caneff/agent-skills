# Trial run: one real ticket through the plain-worktree lane (#705)

Date: 2026-09-12. Map: [Orca exit](https://github.com/caneff/agent-skills/issues/700).
Contract under test: [#703 resolution](https://github.com/caneff/agent-skills/issues/703).
Ticket ridden: sudokumaker-custom-constraints #395 (minify_js prune), picked by Chris.

## Dispatch log

| Step | Result |
|---|---|
| Preconditions | herdr 0.9.0 server running; `hasCompletedOnboarding` true |
| Claim | #395 assigned to caneff |
| Worktree | `git worktree add .claude/worktrees/implement-395 -b implement-395 origin/main` — clean |
| Trust pre-seed | `projects[<worktree>].hasTrustDialogAccepted = true` written to `~/.claude.json` |
| `herdr worktree open --path … --label implement-395 --no-focus` | workspace w4, pane w4:p1 |
| `herdr agent start … --kind claude --pane w4:p1 -- --model sonnet` | ready in one try, `interactive_ready: true`, no dialog |
| `herdr agent prompt … "/implement 395 …" --wait --until working` | `working` observed; no stall |

Dispatcher stopped after the prompt. Worker stays alive through review.

## What hurt (spec tickets are cut from these)

1. **Agent name cap.** herdr rejects names over 32 chars
   (`invalid_agent_name`). `<repo>-implement-<n>` is 44 chars for this repo.
   Used `smcc-implement-395`. The contract needs a naming rule: a repo alias
   or `implement-<n>` alone with the repo read from the pane's cwd.
2. **Default-branch lookup fails.** `implement/SKILL.md` reads
   `git symbolic-ref --short refs/remotes/origin/HEAD`; this repo has no
   `origin/HEAD` ref, so the worker's front-door check errors. Used
   `origin/main` by hand.
3. **Stale worktree dirs.** `.claude/worktrees/agent-ae18…` and
   `agent-afe2…` exist in the repo (Claude Code's own `EnterWorktree`
   leftovers). The dispatch's "path already exists" guard only looks at
   `implement-<n>`; cleanup of `agent-*` needs an owner.
4. **A session lives in the primary checkout.** `herdr agent list` showed an
   idle Claude agent in `~/src/sudokumaker-custom-constraints` itself
   (pane w1:p1, "Herdr notification test"). The #477 yardstick says none.
   Left alone; not mine to end.
5. **The worker's skill still speaks Orca.** Build says "dispatch as one Orca
   worker"; two `orca-ide worktree set` status lines; the report step names
   `worker_done`. Worked around by a brief that says build inline and log
   every Orca line hit under "Lane friction" in the PR body. The brief is
   therefore not the bare `/implement <n>` the contract specifies until the
   skill is rewritten.

## Still to observe (Chris, through herdr)

- Whether `~/.claude/sessions/<pid>.json` writes `waiting` on a permission
  prompt, and whether herdr flips to `blocked` at the same moment.
- Whether the PR body's "Lane friction" list adds items the dispatcher did
  not see.
- `merge-cleanup implement-395` after merge: does the live-session guard
  refuse while the pane is open, and does `herdr workspace close` follow.
