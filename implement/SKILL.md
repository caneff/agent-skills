---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

When the work maps to a GitHub issue, claim it first, so a second client running
this skill can't pick up the same ticket. Read its labels: if it isn't
`ready-for-agent` — already `in-progress`, or handed to a human — stop and ask,
since someone likely holds it. Otherwise take it:

`gh issue edit <n> --remove-label ready-for-agent --add-label in-progress --add-assignee @me`

That pulls it out of every other client's queue. The read-then-flip has a
sub-second race if two clients start on the same ticket at the same instant; for
a handful of clients it is enough. If you abandon the run before a PR is open,
put it back: `gh issue edit <n> --remove-label in-progress --add-label ready-for-agent`.

**Then pick the model.** A `ready-for-agent` ticket that touches no engine or
constraint-modeling logic — a doc edit, a rename, a boundary move, a
tracer-bullet the spec already pins — is Sonnet work. Hand the build to a Sonnet
subagent instead of running it here: `handoff sub` with `model: sonnet`, seeded
with the issue reference, its spec, and the build steps below (worktree → TDD →
`/code-review` → `pushpr`), so the subagent runs them directly rather than
re-invoking this skill; it reports back when the PR is open. Run the current
model only when the ticket reaches those subtle seams, where a wrong answer
still passes the gate.

Before creating the worktree, check the original checkout is clean
(`git status`). The worktree branches from the pushed main, so anything left
uncommitted there is invisible inside it — and copying it across leaves two
copies of the same file to diverge and collide when the branch ships.

Tracker and spec files are the usual offenders, since editing a ticket is not
itself worktree work. Commit those to main and push them before starting; they
are documents with nothing to break. Uncommitted *code* means work in progress
that a ticket branch should not silently absorb — stop and ask.

Then create and switch to a new git worktree for this work (use the
EnterWorktree tool, or `git worktree add`). If already in a dedicated worktree
for this task, stay there. All work happens in the worktree, never the original
checkout.

Implement the work described by the user in the spec or tickets.

Invoke the `tdd` skill before writing any implementation code. Each ticket
names its seams under test — those are the pre-agreed seams; if a ticket
doesn't name any, ask the user for them before starting.

For each acceptance criterion: write the failing test first, run it, and show
it failing, before writing the code that makes it pass. Do not write
implementation ahead of a red test.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the worktree's branch. When a ticket maps to a GitHub
issue, put a closing keyword (`Closes #<n>`) in the final commit body — a bare
`(#<n>)` mention links the issue but does not close it, so `pushpr`'s PR
inherits the mention and merging leaves the issue open.

Once the PR is open, move the ticket to review:
`gh issue edit <n> --remove-label in-progress --add-label in-review`. `in-review`
is the PR-pending-human-merge state the orchestrator also uses, so the issue
reads as done-and-waiting rather than dropped.
