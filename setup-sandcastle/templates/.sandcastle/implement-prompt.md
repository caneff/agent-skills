# TASK

Fix issue {{TASK_ID}}: {{ISSUE_TITLE}}

Pull in the issue using `gh issue view <ID>`. If it has a parent PRD, pull that in too.

Only work on the issue specified.

Work on branch {{BRANCH}}. Make commits and run tests.

# CONTEXT

Here are the last 10 commits:

<recent-commits>

!`git log -n 10 --format="%H%n%ad%n%B---" --date=short`

</recent-commits>

# EXPLORATION

Explore the repo and fill your context window with relevant information that will allow you to complete the task.

Pay extra attention to test files that touch the relevant parts of the code.

# EXECUTION

First decide whether this issue has **new observable behavior** to drive out
test-first. Pure deletions, refactors, doc/config edits, and "move X to Y" tasks
usually do not — their acceptance criteria are end-state facts (a file is gone, a
script no longer exists, a string is present), not behavior. Forcing red-green
onto these produces filesystem-shape assertions dressed up as TDD slices — the
exact "crap tests" `/tdd` warns against.

- **No new behavior** (deletion / refactor / docs / config): skip red-green. Make
  the change, then assert the end-state as plain verification (or just confirm the
  existing suite still passes). Do not manufacture a test file to have something
  to go RED on.
- **New behavior**: use the **`/tdd` skill** and follow it — do not improvise
  your own test rhythm. Its load-bearing rules:
  one vertical slice at a time (RED: one failing test → GREEN: minimal code to
  pass → REPEAT), never write all tests first then all code, test observable
  behavior through the public interface (not source shape), refactor only once
  green.

# FEEDBACK LOOPS

Before committing, run `just check` to ensure lint, type checks, and tests pass.

# COMMIT

Make a git commit. The commit message must:

1. Include task completed + PRD reference
2. Key decisions made
3. Files changed
4. Blockers or notes for next iteration

Keep it concise.

# THE ISSUE

If the task is not complete, leave a comment on the issue with what was done.

Do not close the issue - this will be done later.

Once complete, output <promise>COMPLETE</promise>.

# FINAL RULES

ONLY WORK ON A SINGLE TASK.
