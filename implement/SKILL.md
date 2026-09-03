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
- Typecheck and single test files as you go, the full suite once at the end.
- A pre-existing bug, performance concern, or unmentioned behavior found
  along the way: don't fix or extend it unless the ticket's behavior cannot
  work without it — report it as a follow-up. Scratch checks need not become
  committed tests; commit roughly one focused test per acceptance criterion,
  sized like the neighboring test files.
- Commit to this branch; the driver pushes.

## Finish

Use `/code-review`, and fix what it raises.

Commit to the workspace's branch. When the ticket maps to a GitHub issue, put a
closing keyword (`Closes #<n>`) in the final commit body — a bare `(#<n>)` links
the issue but does not close it. **That trailer is the only thing that closes
the ticket**, and it fires when the commit reaches the default branch.

Then open a PR and set the card to `in-review`. The owner merges; you never do.

If `origin`'s owner is not the person you are working for, push the branch and
stop — hand them the `gh pr create` line instead of opening it yourself.
