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
   gh pr view --json number,title,url,state,mergeStateStatus,reviewDecision,statusCheckRollup
   ```

   - If there is **no PR** for this branch, say so and offer to open one (`gh pr create` is allowed — you may run it). Then stop; shipping comes after a PR exists.
   - If the current branch **is** `main`/`master`, stop and warn — there is nothing to ship.

2. **Report readiness** in one short block: PR number + title, CI/check rollup (pass/fail/pending), review decision, and `mergeStateStatus` (e.g. CLEAN, BLOCKED, BEHIND). If checks are failing or the PR is BLOCKED, say so plainly — don't bury it.

3. **Confirm the merge strategy** with the user if they didn't specify: `--squash` (default), `--merge`, or `--rebase`. Default to deleting the branch after.

4. **Hand off.** Print the exact command for the user to run, prefixed with `! ` so it runs in their shell. Chain the local main-sync onto the merge with `&&` so it fires automatically once the merge succeeds:

   ```
   ! gh pr merge <number> --squash --delete-branch && ~/.claude/hooks/sync-main-after-merge.sh --now
   ```

   If the user has the `ship` shell function installed, this shorthand is equivalent:

   ```
   ! ship <number> --squash --delete-branch
   ```

   Tell them to run the line themselves — make clear you cannot run it for them; that separation is the whole point of the guardrail. The trailing `--now` sync fast-forwards their local main and prunes merged branches the moment the merge lands (replacing the dormant PostToolUse hook).

## Tone

Be terse and operational. This is a release gate, not a lesson — give the readiness facts and the command, nothing more.
