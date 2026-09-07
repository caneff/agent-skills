---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

You are already in the right place. An Orca workspace is its own branch,
checkout, and terminal, so this skill never creates, switches, or removes one.
If you are sitting on the repo's default branch and the work needs a branch,
stop and say so — the workspace should have been made from the ticket.

You are the **driver**: claim, brief, review, commit, PR. The build itself
runs as an Orca worker so the model is chosen per ticket — see Build. Orca
dispatch is the only spawn path; Claude Code's own subagent tools give a build
no task, no preamble, and no `worker_done`.

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
  it arrives: the path the dispatch names (`burndown` seeds
  `~/.cache/burndown/addenda/<n>.md`), else `/tmp/addenda-<n>.md`. Outside the
  checkout, like the report. Finish checks each entry against the diff, and an
  unrecorded message cannot be checked.
- Commit to this branch; the driver pushes.

### The report

An Orca build or fix worker sends exactly one report, in this shape. It is
worded here and nowhere else; `burndown` and `implement-spec` bind their
workers to it by pointer. Reviewers are not covered —
`two-axis-code-review` carries its own report shape and its own caps.

1. **Write the full report to a file first**, in the directory the dispatch
   names (`burndown` seeds `~/.cache/burndown/findings/`); with none named,
   `/tmp`. Never inside the checkout: an untracked report there blocks the
   worktree's teardown. Name it `report-<n>.md` — `<n>` the ticket number,
   `report-<n>-r<round>.md` for a fix round — so the path is derivable when
   the message carrying it is not.
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
at most three times. If the third pass is still not clean, stop: park the
ticket, report what is still open and why, and hand it to the owner. Passes
four through seven cost as much as the build and settle nothing that three did
not — they are where reviewers start re-raising decisions already settled. A
finding you dispute is not a fourth pass either: record it as
`disputed: <why>` and let the owner rule.

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
