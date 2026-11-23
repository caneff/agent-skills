## Rules

- **No git writes.** You do not commit, stage, stash, checkout, reset, rebase or push. The controller commits. The mutation check below runs in the script's own throwaway worktree, not yours. `git status`, `git diff` and `git log` are fine.
- **No nested subagent.** You do your own reading, editing and running. A nested agent reports to the top-level session, not to you, and its work is lost. A task too large for you is reported as such and stopped.
- **Edit only your own files.** The worktree is shared with the other workers; a file listed under Off limits is read-only for you, even to fix something that looks wrong. Report it instead.
- **Mutation checks never touch the live file, and never run in a byte copy or a runner of your own.** The worktree is shared with the other workers, so a live mutation can turn their tests red for a reason that is not theirs. A byte copy of a linked worktree (`cp -r`, `rsync`) is no isolation either: its `.git` file points at the live gitdir, so a git command in it writes the live index and HEAD. `witness-check.sh` is the only way to run a mutation: it makes the throwaway worktree, runs the covering test in it and removes it. One call per mutation (`<id>` is letters, digits, `.`, `-`, `_`); `--with-working-tree` makes the witness the tree as it stands, your uncommitted edits and untracked files included, since you cannot commit:

  ```
  bash ~/.agents/skills/multi-axis-code-review/witness-check.sh --worktree {worktree} --with-working-tree --no-ledger --id {worker}-<id> --file <your file> --old '<text, once>' --new '<replacement>' --test '<the covering test command>'
  ```

  Read its message under your id: `red` carries the failing output, and it must be your assertion, not a missing file; `HOLLOW` means the test passed with the mutation, and `unknown` means it never ran, so report that and not a pass. `--old` must occur exactly once in the file or the call is refused with the count. Never mutate the live file and re-edit it, and never undo a mutation with `git checkout`, `git restore` or `git show HEAD:<file>`: the script discards its own worktree. If the script refuses or cannot run, report that verbatim as `Mutation: not run — <why>` and leave the check to the controller. (Chris, 2026-10-14, #1550; #1696; #1708.)

## Report

Reply with, in this order:

1. `Files changed:` the paths you edited.
2. `Test:` the covering-test command and its result line.
3. `Mutation:` the `--old`/`--new` change you made and the red message it produced, or why none applies.
4. `Out of scope:` anything you saw in a file that is not yours, one line each.
5. `Findings:` only when your brief has a "Findings to fix" section: the per-id lines its "Findings report" section asks for.
