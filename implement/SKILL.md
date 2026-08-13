---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

When the work maps to a GitHub issue, claim it first, so a second client running
this skill can't pick up the same ticket. Read its labels first:

- **`ready-for-agent`** — yours to build from scratch. Take it (below).
- **`ready-for-human`** — the work already exists and is waiting on a human's
  judgment; running `/implement` on it means *you are standing in as that human
  review*. Diff the branch and apply the clear reviewer-grade fixes yourself — a
  wrong citation, a stale comment, a lint miss, anything with one right answer
  and no ask needed. But any genuine **judgment call** the review surfaces — a
  knowing deviation, a semantic-contract choice, anything with more than one
  defensible answer — **stop and put it to the human before you act on it, and
  before you open the PR.** Do not fold it into a "noted" line and ship past it;
  being the review means asking the questions the review raises, not just the
  legwork. Then claim it the same way, swapping `ready-for-human` for
  `ready-for-agent` in the command below.
- **`in-progress`, or otherwise actively held by someone** — stop and ask, since
  someone likely holds it.

To take it:

`gh issue edit <n> --remove-label ready-for-agent --add-label in-progress --add-assignee @me`

That pulls it out of every other client's queue. The read-then-flip has a
sub-second race if two clients start on the same ticket at the same instant; for
a handful of clients it is enough. If you abandon the run before a PR is open,
put it back: `gh issue edit <n> --remove-label in-progress --add-label ready-for-agent`.

**First, pick the model — before choosing a lane, and say the pick out loud.**
Does this ticket touch engine or constraint-modeling logic? **No** (a doc edit,
a rename, a boundary move, a tracer-bullet the spec already pins) → it is Sonnet
work: hand it to a Sonnet subagent — `handoff sub` with `model: sonnet`, seeded
with the issue reference, its spec, and the build steps below (worktree → TDD →
`/code-review` → `pushpr`) so the subagent runs them directly rather than
re-invoking this skill, and it reports back when the PR is open. Stop running it
here. **This holds even for a docs-only ticket that auto-ships to main** — that
lane skips the worktree flow below, so it is the one most likely to sail past
this gate on the current model. **Yes** → run it on the current model, where a
wrong answer at a subtle seam still passes the gate. State which model you
picked and why before doing anything else.

**A subagent can't accept an approval you relay.** If mid-build the ticket hits
a step that needs a stop-and-ask sign-off (an irreversible deletion, a new
dependency, a schema change), the subagent will — correctly — refuse it: no
agent's message counts as the human's consent, so "the coordinator says the
owner approved" does not clear the bar. Route that step back to *this* session,
which holds the real approval; this session performs the gated step, then the
subagent resumes. Don't push it onto the subagent — it cannot verify the
approval came from the human, and trying is permission-laundering.

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
