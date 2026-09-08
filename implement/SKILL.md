---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Two front doors, and `git branch --show-current` picks which one you came in
by. Inside an Orca workspace — its own branch, checkout, and terminal — you
are the driver: skip to § Claim the ticket. Sitting on the repo's **default
branch**, you are not: § Dispatch from the default branch is your whole run,
and every section after it belongs to the worker you hand off to.

You are the **driver**: claim, brief, review, commit, PR. The build itself
runs as an Orca worker so the model is chosen per ticket — see Build. Orca
dispatch is the only spawn path; Claude Code's own subagent tools give a build
no task, no preamble, and no `worker_done`.

## Dispatch from the default branch

The primary checkout is the one tree every session's `merge-cleanup`
fast-forwards, so the work gets a workspace and the workspace gets the build.
Make one here, dispatch into it, and stop — you never claim, never
`git checkout -b` in place, and never build on this branch.

1. **Resolve the ticket.** An explicit number is the ticket. `next` is the
   lowest-numbered open issue labelled `ready-for-agent`:

   ```
   gh issue list --repo <owner/name> --label ready-for-agent --state open
   ```

   An empty queue is the whole answer: say so and stop.

2. **Create the workspace**, named `implement-<n>` — the shape `burndown`
   dispatches under, and what `merge-cleanup` and
   `orca-ide worktree rm --worktree <full branch name>` select on. Orca
   derives the branch from that name and puts the agent in the workspace's
   first terminal:

   ```
   orca-ide worktree create --repo path:<absolute primary checkout> \
     --name implement-<n> --no-parent --base-branch <default branch> \
     --issue <n> --agent claude --prompt "/implement <n>" --json
   ```

   The brief is that pointer and nothing else: this same skill, run from
   inside the workspace, takes the driver's path above.

3. **Confirm the branch** before you report. Read it back rather than
   assuming the name Orca derived:

   ```
   git -C <new worktree path> branch --show-current
   ```

   It must name this ticket's own branch. A reused workspace name has left
   Orca sitting on the base branch itself, where the worker would commit onto
   whatever that base is; fix it with `git checkout -b` there and tell the
   worker.

4. **Report the workspace and stop.** Name the worktree path and the branch
   you dispatched to. The build runs over there; this session is done.

## Claim the ticket

When the work maps to a GitHub issue, claim it before starting, so a second
client cannot pick up the same one. Read its labels first:

- **`ready-for-agent`** — yours to build. Take it.
- **`ready-for-human`** — the work exists and waits on a human's judgment.
  Running this skill means *you are standing in as that review*. Apply the
  reviewer-grade fixes that have one right answer — a wrong citation, a stale
  comment, a lint miss. Put every genuine **judgment call** to the owner before
  you act on it and before the work lands. Then claim it the same way, swapping
  `ready-for-human` for `ready-for-agent` below.
- **`needs-info`** — open questions block the build. Run `/grill-with-docs`
  to resolve them with the owner first; only then relabel and build.
- **`in-progress`, or otherwise held** — stop and ask.

```
gh issue edit <n> --remove-label ready-for-agent --add-label in-progress --add-assignee @me
```

Abandoning the run before the work lands? Put it back:
`gh issue edit <n> --remove-label in-progress --add-label ready-for-agent`

The GitHub label is the record. The workspace card is a local mirror — set it
too, and update it at real checkpoints so progress is visible without opening
the terminal:

```
orca-ide worktree set --worktree active --workspace-status in-progress --json
orca-ide worktree set --worktree active --comment "repro'd; writing the failing test" --json
```

Use `$ORCA_CLI_COMMAND` when Orca exports it.

## Build

Dispatch the build as one Orca worker in this workspace — one Run, one Task —
with the model chosen for this ticket: `sonnet` for an ordinary one, `opus` for
a subtle seam. The loop mechanics (guide to load, waiting, release) are
`implement-spec/SKILL.md`; read it. A change of a few lines with no seam to
test: build it inline, following the same rules.

The brief is pointers, not prose — the ticket URL and its named seams — and
these rules, which bind the worker, or you when you build inline:

- Invoke the `tdd` skill before any implementation code. The ticket's seams
  under test are the pre-agreed seams; if it names none, ask before starting.
- For each acceptance criterion: failing test first, shown red, then the code
  that makes it pass. Implementation follows a red test.
- Once a new or changed test is green, strip the constraint it claims to
  verify (revert the fix, comment out the check), confirm it now fails,
  then restore it. One that still passes is a hollow witness — fix it or
  drop it, never commit it. `two-axis-code-review` runs the same check
  at Finish.
- Typecheck and single test files as you go, the full suite once at the end.
- A pre-existing bug, performance concern, or unmentioned behavior found
  along the way: don't fix or extend it unless the ticket's behavior cannot
  work without it — report it as a follow-up. Scratch checks need not become
  committed tests; commit roughly one focused test per acceptance criterion,
  sized like the neighboring test files.
- Record every message that arrives mid-build — an owner's terminal message,
  a coordinator addendum — as its own entry in the **addenda file**, the moment
  it arrives, at `~/.cache/burndown/<repo dir name>.addenda-<n>.md` — the same
  cache directory as the report (§ The report), outside every checkout, and
  `mkdir -p`'d before the first append. Finish checks each entry against the diff, and an
  unrecorded message cannot be checked.
- Commit to this branch; the driver pushes.

### The report

An Orca build or fix worker sends exactly one report, in this shape. It is
worded here and nowhere else; `burndown` and `implement-spec` bind their
workers to it by pointer. Reviewers are not covered — their own
file-plus-pointer contract is `two-axis-code-review/SKILL.md` § 4's, along
with their report shape and word caps.

1. **Write the full report to a file first**, at
   `~/.cache/burndown/<repo dir name>.report-<n>.md` — `<n>` the ticket
   number, `.report-<n>-r<round>.md` for a fix round — so the path is
   derivable when the message carrying it is not. That cache directory is the
   one home for a run's files whatever the lane, and it exists outside every
   checkout: an untracked report inside one blocks the worktree's teardown.
   `mkdir -p` it before the first write; never fall back to a bare `/tmp`,
   where a path nobody derived is a path nobody finds.
2. **Send one message with the message tool**: `SendMessage`, or Orca
   `worker_done`, as the lane dictates. Verdict first — any question that
   timed out and the choice made — then what changed, the path from step 1,
   and the test line and commit sha last when the round produced them. About
   60 lines or 300 words: a longer message is truncated in transit and the
   coordinator reads a cut-off verdict.
3. **Then stay quiet** until pinged, with no background wait armed. The file
   holds the detail, and the coordinator opens it when the message is not
   enough.

## Finish

Run both reviews and fix what they raise:

1. `/code-review` — the built-in correctness review (bugs, reuse, efficiency,
   CLAUDE.md conventions). It runs at the session's effort level; no argument
   needed.
2. `/two-axis-code-review` — this repo's two-axis review (documented coding
   standards + the originating spec).

Neither one produces the other's findings. Both run, every time.

**Three passes, then park.** A review that raises findings is fixed and re-run,
at most three times — the same cap `implement-spec` § Landing runs its loop
under. If the third pass is still not clean, stop: park the
ticket, report what is still open and why, and hand it to the owner. Passes
four through seven cost as much as the build and settle nothing that three did
not — they are where reviewers start re-raising decisions already settled. A
finding you dispute is not a fourth pass either: record it as
`disputed: <why>` and let the owner rule.

**A gate failure is not a review pass.** A pass is findings → fix → re-run the
review; only that counts against the cap. Your own mechanical checks failing —
the scope check (`git diff --name-only` outside the ticket's files), the test
seam, `pre-report-gate.sh` — is not a pass: no reviewer ran and nothing was
judged. Fix it and carry on. Two gate failures on one ticket, then park.

**A sha nobody reviewed says so.** When the cap is spent, or the lane runs no
re-review at all (`~/.agents/skills/burndown/SKILL.md` step 5 runs one round),
the PR body names the last reviewed sha and says the commits after it were not
re-reviewed. That line is what the reader gets in place of the pass that did
not run.

Then, only if the diff pushes a file from under 1000 lines to over, run
`~/.agents/skills/thermo-nuclear-code-quality-review/SKILL.md` by pointer —
it carries `disable-model-invocation`, so the slash form will not fire for
you. That threshold is the whole trigger: it is a structural review that
will propose restructuring beyond the ticket, so it stays off by default.

Then the handoff, in order. Every step has a command whose output you read,
and the run is not done until the merge line is handed over.

1. **Addenda check.** List every entry in the addenda file (§ Build) and say,
   per entry, where it is in the diff or why it was declined. An entry that is
   neither is unfinished work — fold it in now, before the commit.

   Then commit to the workspace's branch. When the ticket maps to a GitHub
   issue, put a closing keyword (`Closes #<n>`) in the final commit body — a
   bare `(#<n>)` links the issue but does not close it. **That trailer is the
   only thing that closes the ticket**, and it fires when the commit reaches
   the default branch.

2. **Pre-report gate.** Run it on the sha you are about to report:

   ```
   bash ~/.agents/skills/implement/pre-report-gate.sh <sha>
   ```

   It exits non-zero on a dirty tree or on a sha that is not an ancestor of the
   branch tip — the two ways a "done" report has described work that was not on
   the branch. Quote its pass line in the report. Fix commits stack: never
   amend or rebase a sha already reported.

3. **Push, open the PR, confirm it.**

   ```
   git push -u origin <branch>
   gh pr create --repo <owner/name> --fill
   gh pr ready <n> --repo <owner/name>        # only if it opened as a draft
   gh pr view <n> --repo <owner/name> --json isDraft,mergeStateStatus
   ```

   `--fill` builds the body from the commits, so when the unreviewed-sha line
   above applies it is not in there — pass `--body` yourself and put it in.

   The last command must print `false` and `CLEAN` before you go on;
   `UNKNOWN` means GitHub has not finished computing mergeability, so poll it
   for a few seconds. Then set the card:
   `orca-ide worktree set --worktree active --workspace-status in-review --json`.

4. **Hand the merge line.** The owner merges; you never do.

   ```
   ! gh pr merge <n> --repo <owner/name> --squash
   ```

   No `--delete-branch` while an Orca workspace holds the branch — git refuses
   to delete a branch a worktree has checked out, and the merge line fails on
   it. Pair it with the cleanup line instead, which tears the workspace down by
   full branch name, deletes the branch local and remote, and fast-forwards the
   primary checkout:

   ```
   ! cd <absolute primary checkout> && merge-cleanup --repo <absolute primary checkout> <full branch name>
   ```

   Expand both paths yourself. `--repo` defaults to the shell's cwd, and this
   line is pasted from the workspace the cleanup is about to delete — a
   relative run would tear down its own checkout mid-step.

If `origin`'s owner is not the person you are working for, push the branch and
stop — hand them the `gh pr create` line instead of opening it yourself.
