# TASK

Open ONE pull request into `main` for the issues listed at the bottom of this
prompt — they are one dependency component of this run (the orchestrator opens a
separate PR per component). Do NOT open a PR per branch. Do NOT merge the PR into
`main`.

The PR head branch is: `{{MERGE_HEAD}}`

# THE HEAD BRANCH IS ALREADY BUILT AND PUSHED

The orchestrator already assembled `{{MERGE_HEAD}}` as a throwaway head off
`main`: it merged in this component's leaf tips (each of which already contains
its whole chain) and pushed the result to `origin`. **Do NOT create, rebuild,
merge, rebase, or otherwise run git that mutates anything.** The head is final —
your only job is to open ONE pull request from it and write its prose.

Read-only inspection to write an accurate body is expected:

- `git fetch origin main {{MERGE_HEAD}}`
- `git log --oneline origin/main..origin/{{MERGE_HEAD}}` — these are the commits the PR contains.
- `git diff origin/main...origin/{{MERGE_HEAD}}` — the full diff, for writing the body below.

(CI runs lint/typecheck/test on the PR — that is the authoritative gate, so you
do not run them here.)

# OPEN THE PR

Do this in order, in one pass:

1. `mkdir -p .sandcastle/logs`, then write the PR body (sections below) to
   `.sandcastle/logs/pr-body.md`. Write it there, never in the repo root: that
   directory is gitignored, so the body cannot leave the checkout dirty. A stray
   untracked file in the root makes every later `git status` read dirty, which
   breaks any tooling that treats a clean tree as its go signal. The `mkdir`
   matters because `logs/` is gitignored and so is absent from a fresh worktree
   or clone.
2. `gh pr create --base main --head {{MERGE_HEAD}} --title "Sandcastle: <N> issue(s)" --body-file .sandcastle/logs/pr-body.md`
   where `<N>` is the number of issues actually folded in.

**Use `--body-file`, never inline `--body`.** The body contains backticks and
`#`; passed inline they trigger shell command substitution and corrupt the PR.

Build the body in `.sandcastle/logs/pr-body.md` with these sections:

## Summary

One or two sentences on what this run delivered overall.

## Changes

One subsection per issue that made it in. For each:

- A `### #<id> — <title>` heading.
- 1-3 bullets describing the actual change (read the issue's commits/diff with
  `git log` / `git diff origin/main...origin/{{MERGE_HEAD}} -- <paths>`; describe
  behavior, not file lists).
- A `Closes #<id>` line so the squash-merge auto-closes every issue.

## QA checklist

A checklist of concrete things I should verify myself before approving. Include
one item per user-visible change, plus any risky or uncertain area you hit while
merging. Derive each item from the actual diffs in this run, not generic
boilerplate, and favor things a human must verify that the automated tests do
not cover. Examples of the right altitude (adapt to the real changes):

- [ ] Run `<the new CLI subcommand>` against a real input; confirm the output
      matches the issue's acceptance criteria.
- [ ] Point the pipeline at a large/edge-case document; confirm no unhandled
      exception and the result is sensible.
- [ ] Check the migration/config change against an existing environment, not
      just a fresh one.

# AFTER OPENING

Do NOT push to `main`. Do NOT merge the PR. Do NOT touch issue labels — the
orchestrator manages issue lifecycle state (ready-for-agent → in-review →
closed) host-side. The `Closes #<id>` lines close each issue when I
squash-merge the PR manually.

# ISSUES (reference)

{{ISSUES}}

Once the single consolidated PR is open, output <promise>COMPLETE</promise>.
