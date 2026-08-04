---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

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
