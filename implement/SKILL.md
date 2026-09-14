---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Two front doors, and `git branch --show-current` picks which one you came in
by — read against the repo's default branch, which is
`git symbolic-ref --short refs/remotes/origin/HEAD` and not assumed to be
`main`. Inside a workspace — its own branch under `.claude/worktrees/` — you
are the **worker**: skip to § The brief. On the default branch you are the
**dispatcher**: § Dispatch is your whole run. On a detached HEAD you are at
neither door: say so and stop.

## Dispatch

```
implement-dispatch <n> [--model sonnet|opus]
implement-dispatch --spec <n> --slots <k> [--model sonnet|opus]
```

`sonnet` for an ordinary ticket, `opus` for a subtle seam — `--spec` mode
defaults to `opus` instead. Plain mode refuses an issue labelled `spec`,
naming `--spec <n> --slots <k>` as the way to dispatch it; that hands the
issue to a nested `/implement-spec` run instead of a worker. For
`/implement next`, resolve the lowest-numbered open `ready-for-agent` issue
first and pass that number:

```
gh issue list --repo <owner/name> --label ready-for-agent --state open \
  --limit 200 --json number --jq 'min_by(.number).number'
```

`implement-dispatch` claims the ticket, creates the workspace, starts the
worker in a herdr pane, and puts the tier and your session name in the brief.
Its refusals are the whole claim rule (`implement-dispatch --help` lists
them); a refusal is the answer, relayed as it stands. Relay its report and end
the dispatch. You stay that worker's **controller** (§ Control) until its
ticket lands.

## The brief

The worker starts with `/implement <n> --tier light|heavy --controller "<name>"`.
The ticket is `in-progress` and assigned to you already; build it.

- **Light** (`documentation` label): § Light tier.
- **Heavy** (no label): § Heavy tier.

Raise yourself from light to heavy the moment your diff turns out to contain
code — anything executed, imported, or wired into the harness, a `SKILL.md`
included — and say so to the controller. Never lower heavy to light: the label
was read before anyone saw the diff, and code landing unreviewed is the
outcome the heavy tier exists to stop.

**Codex builds this one?** `--codex` on the invocation, or the owner saying
their Claude quota is short, moves the build and its reviews to Codex: read
[`codex-lane.md`](codex-lane.md) and follow it instead. Nothing but the
owner's word turns it on.

## Control

The controller is the session named in the brief; what it rules on and what
it escalates is its entry in `~/.agents/skills/CONTEXT.md`. Send it every question and your
finish notice with `SendMessage` to that name — never to Chris. An ordinary
call you make yourself, under an assumption you state, and list under
Decisions made.

## Light tier

1. Make the change on this branch. Commit with `Closes #<n>` in the body — a
   bare `(#<n>)` links the issue without closing it.
2. Land it on the default branch yourself:

   ```
   git fetch origin && git rebase origin/<default>
   git push origin HEAD:<default>
   ```

   The rebase first because a push from a stale base is rejected as a
   non-fast-forward, and a force push would erase someone else's commit.

3. Confirm `gh issue view <n> --repo <owner/name>` shows the issue closed —
   a rebase can rewrite the commit so the trailer never fires.
4. Send the controller the landed sha and the cleanup line:
   `! cd <absolute primary checkout> && merge-cleanup --repo <absolute primary checkout> implement-<n>`.

No PR and no reviewer; Chris reads the log after.

## Heavy tier

### Build

- Invoke the `tdd` skill before any implementation code.
- For each acceptance criterion, write the failing test and see it red before
  the code that makes it pass. Once green, strip the constraint it verifies
  and see it fail, then restore it — a test that passed with the fix reverted
  has shipped as proof of a fix it never checked.
- A pre-existing bug, performance concern, or unmentioned behavior found along
  the way: don't fix it unless the ticket's behavior cannot work without it —
  report it as a follow-up. Why: an unasked fix widens the diff past what the
  reviewers check against the ticket.
- Typecheck and single test files as you go, the full suite once at the end.
  Why: a failure caught at the file it came from is cheaper to place than one
  found in the full run.

### Review

1. One full round of `/multi-axis-code-review`: standards, spec and
   correctness, all three waited for (its § Why separate axes says why the
   built-in `/code-review` is not run here; `/code-review low` only when the
   owner asks). Every finding in the aggregate gets exactly one disposition:
   fixed in a commit, `disputed: <why>`, or filed as a follow-up ticket.
   The PR body lists the disputed and filed ones.
2. One verification pass, scoped to the round-1 findings and the fix commits.
   Pass the reviewers every disputed, ruled, or other-ticket item as settled.
   A round-1 finding with no disposition is the one thing this pass fails
   on.

No third pass. Commits after the verification pass are unreviewed; the PR
body's last reviewed sha says where review stopped.

### Before the PR

1. **`pwd` and `git branch --show-current` match this workspace before every
   commit** — a workspace left sitting on the base branch, or a cwd in another
   session's worktree, puts the commit there.
2. **Scope check**: `git diff --name-only origin/<default>...HEAD` names only
   the ticket's files, or each extra one is listed under Decisions made — a
   file the ticket never named lands with no reviewer looking for it.
3. **`bash ~/.agents/skills/implement/pre-report-gate.sh <sha>`** passes on
   the sha you report — a "done" report has described work that was dirty in
   the tree or not on the branch.
4. **`gh pr view <pr> --repo <owner/name> --json isDraft,mergeStateStatus`**
   prints `false` and `CLEAN` before the merge line goes out — a merge line
   handed over on a draft or a conflicted PR fails in Chris's shell. `UNKNOWN`
   means GitHub is still computing; poll a few seconds.
5. **After merge, `gh issue view <n> --repo <owner/name>` shows each `Closes`
   issue closed** — a squash or rebase can rewrite the commit so the trailer
   never fires.

The final commit body carries `Closes #<n>`. Stack fix commits; never amend a
sha already reported — an amend erases the sha the controller was handed.

### The PR

```
git push -u origin implement-<n>
gh pr create --repo <owner/name> --title "<title>" --body-file <body>
```

The body has these sections and nothing else:

- **What changed** — three lines.
- **Tests run** — the command and its result line.
- **Decisions made** — each with its reason, including every round-1
  finding that was disputed (with the why) or filed (with its ticket number).
- **Last reviewed sha** — and that commits after it were not re-reviewed.

Send the controller "PR up" with the PR URL and these two lines, paths
expanded:

```
! gh pr merge <pr> --repo <owner/name> --squash
! cd <absolute primary checkout> && merge-cleanup --repo <absolute primary checkout> implement-<n>
```

No `--delete-branch`: git refuses to delete a branch a worktree has checked
out, and the merge fails on it; `merge-cleanup` removes the workspace and
deletes the branch after. The paths are absolute because the line is pasted
from the workspace it deletes.

## Someone else's repo

When `origin`'s owner is not Chris, either tier: commit on the branch, and
send the controller the push and `gh pr create` lines instead of running them.
The git hook blocks every push to a repo Chris does not own, and Chris sees
the work before any other human does.
