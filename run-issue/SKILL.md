---
name: run-issue
description: Manually run a single issue through the Sandcastle pipeline — spawn one subagent to implement it on a branch, then a second subagent to review that branch's diff. Use when the user wants to run/build an issue "like Sandcastle would", manually run an issue with implementer + reviewer subagents, or process issue number N without the full orchestrator.
---

# Run Issue

Reproduce one Sandcastle issue pipeline by hand: **implement → review**, two subagents, on a dedicated branch. No orchestrator, no PR, no push.

## Input

An issue number `N` (from `/run-issue N` or the user's message). Branch is `sandcastle/issue-N`.

## Steps

1. **Branch.** From the repo's default branch, create `sandcastle/issue-N` (or check it out if it exists). Stay on it.

2. **Resolve prompts.** If `.sandcastle/implement-prompt.md` and `.sandcastle/review-prompt.md` exist, use them verbatim (they ARE the real pipeline) — substitute placeholders and pass as the subagent prompt. Otherwise use the embedded fallbacks below. Placeholders: implement → `{{TASK_ID}}`=N, `{{ISSUE_TITLE}}`=the issue title (`gh issue view N`), `{{BRANCH}}`=`sandcastle/issue-N`; review → `{{BRANCH}}`=`sandcastle/issue-N`, `{{REVIEW_BASE}}`=the base branch (default `main`). A repo prompt may contain a line that starts with an exclamation mark immediately followed by a backtick-quoted shell command (bang-prefixed inline command) — tell the subagent these mean "run that command and use its output."

3. **Spawn the implementer** (one subagent, e.g. `general-purpose`) and WAIT for it. It works only on `sandcastle/issue-N`, commits on that branch, runs the repo's typecheck/test gates, and must NOT push, open a PR, or close the issue.

4. **Gate on work.** `git diff <base>...sandcastle/issue-N --name-only`. If empty, stop and report "no work produced" — do not run the reviewer (matches Sandcastle's `branchHasWork` gate).

5. **Spawn a FRESH reviewer** (brand-new `Agent` spawn, never a `SendMessage` continuation of the implementer) and WAIT. Its prompt contains ONLY the issue text, the branch's commit message(s) (`git log <base>..branch`), and the diff (`git diff <base>...branch`) — NOT the implementer's receipt, reasoning, or narration. It reviews `<base>...sandcastle/issue-N`, may commit refinements on the same branch, and runs the gates. Same no-push/no-PR/no-close rule. (The repo's `review-prompt.md`, when used, already builds context from the diff + commits — keep it that way; don't inject implementer context.)

6. **Stop.** Report what each subagent did. Print the push command for the user to run themselves (push is guardrail-blocked):
   `!git push -u origin sandcastle/issue-N`
   Do not push, open the PR, or close the issue.

## Rules

- Two subagents, sequential — never review before implementing, never skip the work-gate.
- All commits stay on `sandcastle/issue-N`. The host (you) only branches and gates; the subagents do the code and git commits.
- Relay each subagent's final receipt to the user; their output is not shown directly.

## Fallback prompts (no `.sandcastle/*` prompts present)

**Implementer:** "Implement issue N (`gh issue view N`) on branch `sandcastle/issue-N`, this issue only. Explore the repo first. Use red-green-refactor: write a failing test, make it pass, repeat, then refactor. Run the project's typecheck and test scripts before committing. Commit on this branch with a clear message. Do NOT push, open a PR, or close the issue. Report a tight receipt: files changed, key decisions, gate results."

**Reviewer:** "Review the diff `<base>...sandcastle/issue-N` for correctness, clarity, and the repo's coding standards without changing behavior. Verify edge cases and that new behavior is tested. Apply safe refinements directly on the branch and re-run the gates; if it's already clean, make no commit. Do NOT push, open a PR, or close the issue. Report findings and any commit you made."
