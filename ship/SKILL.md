---
name: ship
description: Prepare the final merge of the current branch's PR and hand it off to the user to run. Use when the user wants to ship, merge, or land their PR on main, or says "ctm".
disable-model-invocation: true
user-invocable: true
argument-hint: "[PR number, optional] [squash|merge|rebase, optional]"
---

The user wants to land their work on main. **You do not have authority to push or merge** — a guardrail hook blocks `git push` and `gh pr merge`. Your job is to prepare the merge and hand the user the exact command to run themselves via the `!` prefix, which executes in their shell, outside the hook.

**Never run `gh pr merge` or `git push` yourself.** Doing so is both forbidden by policy and blocked by the hook. You only gather context and print the handoff line.

## Steps

1. **Identify the PR.** If the user gave a PR number, use it. Otherwise find the open PR for the current branch:

   ```bash
   git rev-parse --abbrev-ref HEAD
   gh pr view --json number,title,url,state,mergeStateStatus,reviewDecision,statusCheckRollup,headRefName
   ```

   (With an explicit PR number, run `gh pr view <number> --json ...,headRefName`.) Capture `headRefName` — you need it to detect a worktree pin in step 4.

   - If there is **no PR** for this branch, open one immediately (`gh pr create` is allowed — you may run it). Do not ask first; the user invoking `/ship` with no PR is the request to create it. Then continue to the readiness report and handoff in the same turn.
     - If `gh pr create` fails because the branch is not on the remote (e.g. "No commits between main and <branch>" / "Head ref must be a branch"), the branch was never pushed and push is guardrail-blocked for you. Hand the user **both** lines at once — first pushes and opens the PR, second merges and syncs once the PR exists. Print them as two separate lines so the user can run them in order:
       ```
       ! git push -u origin <branch> && gh pr create --base main --fill-verbose
       ! gh pr merge <branch> --squash --delete-branch && until [ "$(gh pr view <branch> --json state -q .state)" = MERGED ]; do sleep 10; done && ~/.claude/hooks/sync-main-after-merge.sh --now
       ```
       Always use `--fill-verbose` (not `--fill`) so the PR body includes **every** commit's full message, not just the first — the branch may hold several commits. The squash merge then folds them all into one commit on main. (`gh pr merge` accepts the branch name, so the second line works without knowing the PR number yet.) Skip the rest of the steps — both commands are already handed off.
   - If the current branch **is** `main`/`master`, stop and warn — there is nothing to ship.

2. **Report readiness** in one short block: PR number + title, CI/check rollup (pass/fail/pending), review decision, and `mergeStateStatus` (e.g. CLEAN, BLOCKED, BEHIND). If checks are failing or the PR is BLOCKED, say so plainly — don't bury it.

3. **Merge strategy is auto-picked by `ship`** (squash if the PR took post-creation churn, rebase if it's still clean) — don't prompt for it by default. Only pass an explicit `--squash|--merge|--rebase` as ship's second arg when the user asks for one. The branch is deleted after either way.

4. **Hand off.** Print the exact command for the user to run, prefixed with `! ` so it runs in their shell.

   **Default — use the `ship` script.** `~/.local/bin/ship` (on PATH) wraps the whole merge → wait-for-MERGED → sync-main chain in one argument. For the common case (green checks, no worktree pin, repo without `--auto`), this is the handoff:

   ```
   ! ship <number>
   ```

   `ship` auto-picks the merge strategy by churn: it counts commits pushed **after** the PR opened — any such review-fixup churn → `--squash` (fold it into one clean commit), none (the PR still holds its original atomic commits) → `--rebase` (preserve them on main). It then deletes the branch, polls until the PR state is `MERGED`, and fast-forwards local main exactly once. Override the auto-pick with an optional second arg: `ship <number> --squash|--rebase|--merge`. Fall back to the full command below only for behavior `ship` doesn't cover: `--auto` for still-pending checks, or a worktree-pinned branch.

   **Full command** (what `ship` expands to — use directly for the edge cases above). Chain the local main-sync onto the merge with `&&` so it fires automatically once the merge succeeds:

   ```
   ! gh pr merge <number> --squash --delete-branch && until [ "$(gh pr view <number> --json state -q .state)" = MERGED ]; do sleep 10; done && ~/.claude/hooks/sync-main-after-merge.sh --now
   ```

   Plain `gh pr merge` (no `--auto`) merges immediately and requires the checks to be green already; if they're still pending it fails and the user re-runs the line once green. The `until` poll then waits for the merge to actually land before syncing — without it, the sync could fire too early (no-op), forcing a manual resync later. The loop polls every 10s until the PR state is `MERGED`, then fast-forwards local main exactly once. If CI fails, the PR never reaches `MERGED` and the loop keeps polling — Ctrl-C to bail. Backgroundable with a trailing `&` if you don't want to tie up the shell.

   **`--auto` only if the repo allows it.** When checks are still pending, `--auto` queues the merge to fire the moment they pass (no manual re-run). But it is gated on a repo setting: if auto-merge is disabled, `gh pr merge --auto` hard-errors with `Auto merge is not allowed for this repository (enablePullRequestAutoMerge)` and that non-zero exit short-circuits the `&&` chain, so the sync never runs. So detect first:

   ```bash
   gh api repos/{owner}/{repo} --jq '.allow_auto_merge'
   ```

   `true` **and** checks still pending → insert `--auto` before `--delete-branch` in the command above. `false`, or checks already green → leave it out (the plain command shown is correct).

   **Worktree-pinned branch (sandcastle).** `--delete-branch` deletes the *local* branch too, which fails when a worktree has it checked out — and that non-zero exit short-circuits the `&&`, so the sync never runs. Before handing off, check whether `headRefName` is pinned:

   ```bash
   git worktree list --porcelain | grep -B2 "^branch refs/heads/<headRefName>$"
   ```

   If a worktree is listed, prepend its removal so the local delete and the sync both succeed. `--force` because sandcastle worktrees carry untracked scratch; the branch content is already squashed onto main, so nothing tracked is lost:

   ```
   ! git worktree remove --force <worktree-path> && gh pr merge <number> --squash --delete-branch && until [ "$(gh pr view <number> --json state -q .state)" = MERGED ]; do sleep 10; done && ~/.claude/hooks/sync-main-after-merge.sh --now
   ```

   Leave other worktrees (open work) untouched — remove only the one pinning this PR's branch.

   Tell them to run the line themselves — make clear you cannot run it for them; that separation is the whole point of the guardrail. The `until`-then-sync waits for the merge to land, then fast-forwards their local main and prunes merged branches — no early no-op, no manual resync.

## Tone

Be terse and operational. This is a release gate, not a lesson — give the readiness facts and the command, nothing more.
