## Rules

- **No git writes.** You do not commit, stage, stash, checkout, reset, rebase or push. The controller commits. `git status`, `git diff` and `git log` are fine.
- **No nested subagent.** You do your own reading, editing and running. A nested agent reports to the top-level session, not to you, and its work is lost. A task too large for you is reported as such and stopped.
- **Edit only your own files.** The worktree is shared with the other workers; a file listed under Off limits is read-only for you, even to fix something that looks wrong. Report it instead.
- **Mutation checks never touch the live file.** Your worktree is shared with the other workers, so a live mutation can turn their tests red for a reason that is not theirs. Run the check on a copy of the whole worktree, so the covering test finds the mutated file where it expects it:

  ```
  cp -a {worktree} "$(mktemp -d)/copy"
  ```

  Mutate your file in the copy, run the covering test from inside the copy, read the red message (it must be your assertion, not a missing file), then delete the copy. Never mutate the live file and re-edit it. If the test cannot run from a copy, report `Mutation: not run — <why>` and leave the check to the controller. (Chris, 2026-10-14, #1550.)

## Report

Reply with, in this order:

1. `Files changed:` the paths you edited.
2. `Test:` the covering-test command and its result line.
3. `Mutation:` the change you made on the scratch copy and the red message it produced, or why none applies.
4. `Out of scope:` anything you saw in a file that is not yours, one line each.
