## Rules

- **No git writes.** You do not commit, stage, stash, checkout, reset, rebase or push. The controller commits. The one exception is the throwaway mutation worktree below. `git status`, `git diff` and `git log` are fine.
- **No nested subagent.** You do your own reading, editing and running. A nested agent reports to the top-level session, not to you, and its work is lost. A task too large for you is reported as such and stopped.
- **Edit only your own files.** The worktree is shared with the other workers; a file listed under Off limits is read-only for you, even to fix something that looks wrong. Report it instead.
- **Mutation checks never touch the live file, and never run in a byte copy.** The worktree is shared with the other workers, so a live mutation can turn their tests red for a reason that is not theirs. A byte copy of a linked worktree (`cp -r`, `rsync`) is no isolation either: its `.git` file points at the live gitdir, so a git command in it writes the live index and HEAD. Mutate in a throwaway worktree instead, one per mutation (`<id>` is letters, digits, `.`, `-`, `_`):

  ```
  git -C {worktree} worktree add --detach {worktree}/.scratch/mutation-{worker}-<id> HEAD
  git -C {worktree} ls-files -m -o --exclude-standard -z -- . ':!.scratch' | xargs -0 -I% cp --parents % {worktree}/.scratch/mutation-{worker}-<id>/
  ```

  The first line checks out committed `HEAD`; the second carries the other workers' uncommitted edits over, so the covering test sees the tree as it stands. Mutate your file there, run the covering test from inside it, read the red message (it must be your assertion, not a missing file), then undo the mutation by removing the worktree:

  ```
  git -C {worktree} worktree remove --force {worktree}/.scratch/mutation-{worker}-<id>
  ```

  A Rust mutation sets `CARGO_TARGET_DIR={worktree}/.scratch/mutation-{worker}-<id>/target` on its test run, so cargo never reuses the live build dir and leaves a mutated build behind. Never mutate the live file and re-edit it, and never undo a mutation with `git checkout`, `git restore` or `git show HEAD:<file>`: removing the worktree is the only undo. If the removal is refused, report that verbatim and stop. If the test cannot run from the worktree, report `Mutation: not run — <why>` and leave the check to the controller. (Chris, 2026-10-14, #1550; #1696.)

## Report

Reply with, in this order:

1. `Files changed:` the paths you edited.
2. `Test:` the covering-test command and its result line.
3. `Mutation:` the change you made in the mutation worktree and the red message it produced, or why none applies.
4. `Out of scope:` anything you saw in a file that is not yours, one line each.
5. `Findings:` only when your brief has a "Findings to fix" section: the per-id lines its "Findings report" section asks for.
