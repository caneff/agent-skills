# TASK

Open ONE pull request against `{{BASE}}` for a single issue that just passed
review. Do NOT merge the PR. Open it **ready for review**, never as a draft —
two agent reviewers already vetted this branch; it is waiting on a human.

- Issue: **#{{ISSUE_ID}} — {{ISSUE_TITLE}}**
- PR head branch: `{{BRANCH}}` (already built and pushed to `origin`)
- PR base branch: `{{BASE}}`

If `{{BASE}}` is not `main`, this PR is **STACKED**: it targets a sibling PR's
branch instead of `main`, because this issue's work built on top of that
branch within this run. Say so in the PR body (see below) — a human reviewing
it needs to know the stack merges bottom-up, base PR first, or the diff they
see will include the base PR's commits too.

# THE HEAD BRANCH IS ALREADY BUILT AND PUSHED

The orchestrator cut `{{BRANCH}}` from `main`, the implementer committed to it,
and the orchestrator pushed it to `origin`. **Do NOT create, rebuild, merge,
rebase, or otherwise run git that mutates anything.** Your only job is to open
ONE pull request from it and write its prose.

Read-only inspection to write an accurate body is expected:

- `git fetch origin {{BASE}} {{BRANCH}}`
- `git log --oneline origin/{{BASE}}..origin/{{BRANCH}}` — the commits the PR contains.
- `git diff origin/{{BASE}}...origin/{{BRANCH}}` — the full diff, for the body below.

(CI runs lint/typecheck/test on the PR — that is the authoritative gate, so you
do not run them here.)

# OPEN THE PR

Do this in order, in one pass:

1. `mkdir -p .sandcastle/logs`, then write the PR body (sections below) to
   `.sandcastle/logs/pr-body-{{ISSUE_ID}}.md`. Write it there, never in the repo
   root: that directory is gitignored, so the body cannot leave the checkout
   dirty. A stray untracked file in the root makes every later `git status` read
   dirty, which breaks tooling that treats a clean tree as its go signal. The
   `mkdir` matters because `logs/` is gitignored and so is absent from a fresh
   worktree or clone.
2. `gh pr create --base {{BASE}} --head {{BRANCH}} --title "Sandcastle: #{{ISSUE_ID}} {{ISSUE_TITLE}}" --body-file .sandcastle/logs/pr-body-{{ISSUE_ID}}.md`

**Use `--body-file`, never inline `--body`.** The body contains backticks and
`#`; passed inline they trigger shell command substitution and corrupt the PR.

Build the body in `.sandcastle/logs/pr-body-{{ISSUE_ID}}.md` with these sections:

## Summary

One or two sentences on what this issue delivered — describe behavior, not a
file list. If `{{BASE}}` is not `main`, open with a note that this PR is
**STACKED on `{{BASE}}`** and that the stack merges bottom-up — the base PR
first, this one after. End with a `Closes #{{ISSUE_ID}}` line so the
squash-merge auto-closes the issue and unblocks its children on the next run.

## QA checklist

A checklist of concrete things I should verify myself before approving. Include
one item per user-visible change, plus any risky or uncertain area in the diff.
Derive each item from the actual diff, not generic boilerplate, and favor things
a human must verify that the automated tests do not cover. Examples of the right
altitude (adapt to the real changes):

- [ ] Run `<the new CLI subcommand>` against a real input; confirm the output
      matches the issue's acceptance criteria.
- [ ] Point the pipeline at a large/edge-case document; confirm no unhandled
      exception and the result is sensible.
- [ ] Check the migration/config change against an existing environment, not
      just a fresh one.

# AFTER OPENING

Do NOT push to `{{BASE}}`. Do NOT merge the PR. Do NOT touch issue labels — the
orchestrator manages issue lifecycle state host-side. The `Closes #{{ISSUE_ID}}`
line closes the issue when I squash-merge the PR manually.

Once the PR is open, output <promise>COMPLETE</promise>.
