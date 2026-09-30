# No guard hook refuses an in-place restore in a worker's checkout

Status: accepted

## Context

`implement/SKILL.md` § Build says a mutation check runs in a throwaway
worktree and "nothing is restored in the live checkout", because
`git checkout -- <file>`, `git restore` and `git stash` take any uncommitted
edit in the file with the mutation (#1261). Review of PR #1272 (finding S2,
swept into #1273) asked whether that sentence needs a mechanism behind it —
defect class 2 — in the form of a hook that refuses those three commands in
an `implement-*` worktree with a dirty tree.

## Decision

No hook. The rule's mechanism is the recipe, not a guard: § Build's
mutation steps never touch the live checkout, so there is no restore step to
refuse, and `implement/mutation-worktree-wording.test.sh` fails if § Build
names a restore command anywhere outside the sentence that forbids it.

A hook would also refuse work that is sanctioned in a dirty `implement-*`
tree. `~/.claude/CLAUDE.md` names `git checkout --ours|--theirs <paths>`
inside a rebase as allowed, and a rebase conflict is a dirty tree by
definition. The harness's shared-stash guidance prescribes
`git stash push -u -m <tag>` as the way to set work aside. Telling those
apart from a mutation restore needs the command's intent, which a pattern on
the command line does not carry. The hook would also be wired into
user-level settings outside this repo, so a false refusal would land in
every session on the box.

## Consequences

- Reopen this if a worker is seen restoring in place again after #1261's
  recipe landed: that would show the recipe alone does not carry the rule.
- § Build's "Commit the work first" bounds the loss a stray restore can
  cause to edits made since the last commit.
