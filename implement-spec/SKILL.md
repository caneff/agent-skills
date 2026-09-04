---
name: implement-spec
description: "Drive a sliced spec as one supervised Orca run: workers on the ready frontier, one PR, a review loop until clean."
disable-model-invocation: true
---

You are the **coordinator**: a top-level Claude session in the spec's Orca
workspace, started from the spec issue. This file is policy. Every command is
an Orca verb: run `orca-ide skills get orchestration` and
`orca-ide skills get orca-cli` before the first one and follow that grammar,
which is version-matched to the binary. This is supervised orchestration; a
full handoff is a different lane, and the two stay apart.

A mixed-origin queue — several tickets from different specs, not one spec's
slices — is [`burndown`](../burndown/SKILL.md)'s job, not this skill's.

## Shape

One Run for the spec. One Task per ticket, plus an **exploration** task first
that every ticket task depends on; its notes are committed so workers can read
them. Each task's dependencies are the ticket's blocking edges. A ticket
labelled `ready-for-human` is a gate, not a task.

Workers run in this workspace, agent `claude`, model `sonnet` unless the ticket
names opus. The frontier is Orca's ready-task query. Start every ready worker,
then wait.

Set the workspace comment at every checkpoint — a task dispatched, a ticket
landed, a gate raised or resolved, and the Run's end. It is the progress line
the owner reads, and the only surface that shows a gate.

## The brief

The worker rules in `implement/SKILL.md` § Build, by pointer, plus the
**file-ownership map** — the one thing the injected preamble cannot carry:

- Which files this worker owns outright.
- For each shared file, one writer at a time. The handover condition is a
  commit — "a commit referencing #N is in `git log`".
- When a ticket touches one rule of a state machine that lives across files,
  the brief states the whole machine.

## Waiting

Wait for a worker to finish, escalate, or ask. Known failure: the wait verb
returns `waiter_exists` for a waiter nobody can see, and its retry flag does not
attach. Don't use it — use `orca-wait --terminal <handle> --for exit|tui-idle
[--timeout-ms N]` (in `~/.local/bin`), which polls `terminal show` and never
registers a server-side waiter. Exit 0 = condition met, 2 = timeout. Kill any
old wait loop before arming a new one. A duplicate finish message after release
arrives rejected — ack it.

## Gates

A gate is the owner's decision. Gate the Run: `gate-create --task` flips a
completed task to `blocked` and its resolve leaves it `ready`. Surface it two
ways — the workspace comment and the question in your terminal — then **end
your turn**. Orca's NEEDS YOU column stays empty for a gate; the comment and
your idle prompt are the only signals. Resolve the gate after the owner
answers in your terminal.

## Landing

Draft PR at the first commit, closing the spec and every ticket. Push the
branch; the owner merges.

End of spec is a **loop**: a review-only worker runs `/code-review` on HEAD,
and one end-to-end test drives the whole spec — write it if none exists; it is
what catches the bugs the per-ticket suites cannot. Findings become fix tasks;
then review again on the new HEAD. Exit when a pass returns no P0/P1. A fix
brief names the primary signal and the whole state machine; a fix that only
reorders one rule trades a P1 for its mirror.

Then set the card `in-review` with the tally in the comment, and stop.
