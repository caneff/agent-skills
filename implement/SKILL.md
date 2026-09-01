---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

You are already in the right place. An Orca workspace is its own branch,
checkout, and terminal, so this skill never creates, switches, or removes one.
If you are sitting on the repo's default branch and the work needs a branch,
stop and say so — the workspace should have been made from the ticket.

Do the build yourself. Do not hand it to a subagent: the workspace is already
the isolation that delegation used to buy, and Orca's own guidance is not to
substitute other agent-spawn tools for its dispatch.

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

Use `$ORCA_CLI_COMMAND` when Orca exports it. On Linux never run bare `orca` —
it resolves to the GNOME screen reader.

## Build

Invoke the `tdd` skill before writing any implementation code. Each ticket names
its seams under test; those are the pre-agreed seams. If a ticket names none,
ask for them before starting.

For each acceptance criterion: write the failing test first, run it, show it
failing, then write the code that makes it pass. Never write implementation
ahead of a red test.

Run typechecking and single test files as you go, and the full suite once at the
end.

## Finish

Use `/code-review`, and fix what it raises.

Commit to the workspace's branch. When the ticket maps to a GitHub issue, put a
closing keyword (`Closes #<n>`) in the final commit body — a bare `(#<n>)` links
the issue but does not close it. **That trailer is the only thing that closes
the ticket**, and it fires when the commit reaches the default branch.

Then open a PR and set the card to `in-review`. The owner merges; you never do.

If `origin`'s owner is not the person you are working for, push the branch and
stop — hand them the `gh pr create` line instead of opening it yourself.
