---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Before implementing, create and switch to a new git worktree for this work
(use the EnterWorktree tool, or `git worktree add`). If already in a dedicated
worktree for this task, stay there. All work happens in the worktree, never the
original checkout.

Implement the work described by the user in the spec or tickets.

Invoke the `tdd` skill before writing any implementation code. Each ticket
names its seams under test — those are the pre-agreed seams; if a ticket
doesn't name any, ask the user for them before starting.

For each acceptance criterion: write the failing test first, run it, and show
it failing, before writing the code that makes it pass. Do not write
implementation ahead of a red test.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the worktree's branch.
