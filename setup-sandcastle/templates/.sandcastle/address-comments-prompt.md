# TASK

Address the review comments on PR #{{PR_NUMBER}}, push the fixes to its branch,
and reply to each thread. Reply-only: do NOT resolve threads, do NOT merge.

# ORIENT

1. You are already on PR #{{PR_NUMBER}}'s branch — this sandbox checked it out
   in an isolated worktree. Confirm with `git branch --show-current` and
   `gh pr view {{PR_NUMBER}}`. Every commit you make here updates the open PR.
   Do NOT run `gh pr checkout` (it would fail against the existing worktree).
2. Get the repo slug for the API calls below:
   `OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)`.

# GATHER THE COMMENTS

There are two kinds; handle both.

- **Inline review comments** (anchored to a file + line):
  `gh api repos/$OWNER_REPO/pulls/{{PR_NUMBER}}/comments`
  Each has `id`, `path`, `line`, `body`, `user.login`, and `in_reply_to_id`
  (null for the comment that starts a thread). Treat each thread-starting
  comment (`in_reply_to_id == null`) as a unit of work.
- **Top-level comments and review summaries**:
  `gh pr view {{PR_NUMBER}} --json comments,reviews`. A review with state
  `CHANGES_REQUESTED` and any actionable top-level comment also counts.

A comment is **actionable** if it asks for a change. Skip ones that are just
acknowledgements, or that a reply from the PR author already says are handled.

# ADDRESS EACH ONE

For each actionable comment, make the change it asks for, at the file and line
it points to. Stay scoped to what the comment requests — do not refactor
unrelated code.

If a comment is unclear, or you think the requested change is wrong, do NOT
guess. Make no change for that thread and instead reply (below) explaining the
question or your reasoning. A wrong "fix" is worse than a question.

# VERIFY, COMMIT, PUSH

1. Run `just check`. It must pass.
2. Stage everything and commit — use `git add -A`, not `git commit -am`, because
   `-am` skips any NEW file a fix added and it would never reach the PR:
   `git add -A && git commit -m "Address review comments on #{{PR_NUMBER}}"`.
   (The pre-commit hook will re-run lint/format/tests — let it.)
3. `git push` to update the PR.
4. Capture the new commit SHA: `SHA=$(git rev-parse --short HEAD)`.

# REPLY TO EACH THREAD (reply-only)

For every comment you addressed or chose not to, post a reply in its thread.

Run `mkdir -p .sandcastle/logs` once, then write each reply to
`.sandcastle/logs/reply.md` and post the file. Write it there, never in the repo
root: that directory is gitignored, so a reply cannot leave the checkout dirty.
The `mkdir` matters because `logs/` is gitignored and so is absent from a fresh
worktree or clone. Do NOT pass
the reply inline with `-f body="…"` / `--body "…"`: the blockquote `>` and the
backticks around the SHA get mangled by the shell (the backticks run as a command
substitution and the code span vanishes). Substitute the real SHA into the file
as you write it.

- **Inline thread** — reply in the same thread:
  `gh api repos/$OWNER_REPO/pulls/{{PR_NUMBER}}/comments/<comment_id>/replies -F body=@.sandcastle/logs/reply.md`
  where `<comment_id>` is the thread-starting comment's `id`.
- **Top-level** — `gh pr comment {{PR_NUMBER}} --body-file .sandcastle/logs/reply.md`.

Reply content: **start every reply with a Markdown blockquote of the comment you
are responding to** so the thread is self-contained — one or two `> `-prefixed
lines quoting (or, if long, trimming to) the original comment, then a blank line,
then your reply. After the quote: one or two sentences. If you made a change, say
what you changed and reference the commit (e.g. "Dropped the backticks so it
renders as a plain link — `$SHA`."). If you did not change anything, say why or
ask the question.

Example:

```
> Drop the backticks here — this should render as a plain link.

Done — removed them so it renders as a plain link. `$SHA`
```

Do NOT resolve the threads — leave that to the human reviewer. Do NOT merge the
PR. Do NOT close the PR.

Once every actionable comment has a fix (or a reply explaining why not) and the
branch is pushed, output <promise>COMPLETE</promise>.
