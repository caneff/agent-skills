---
name: dispatch-ticket
description: "PROTOTYPE — emit the standard delegated-build brief from a ticket id. Use when the coordinator is about to seed a builder subagent for a claimed ticket and wants the brief generated instead of hand-written."
---

# dispatch-ticket — PROTOTYPE, throwaway

> Assumption (from the br-transfer map, agent-skills #466): this skill never
> names a tracker CLI. Every tracker read/write goes through the repo's
> tracker doc (`docs/agents/issue-tracker.md`, reached via AGENTS.md per
> ADR 0001). If the repo moves from GitHub to `br`, this skill does not change.

A delegated-build brief is the seed prompt the coordinator hands a builder
subagent. This skill generates it from a ticket id so the skeleton stops
being retyped and per-repo hazards stop being carried by hand.

This skill only **emits text**. It does not claim the ticket, spawn the
agent, or touch the repo. The coordinator stays responsible for claiming
(per the tracker doc), picking the model, and holding human-gated steps.

## Inputs

1. **Ticket id** (required) — resolve and read it per the target repo's
   tracker doc: full body plus comments; the LATEST agent brief comment is
   the contract, superseding earlier ones.
2. **Target repo** — the repo the diff lands in. Default: the repo whose
   tracker holds the ticket; override when the ticket names another repo
   (say so in the brief).
3. **Hazards** — if the target repo has `docs/agents/hazards.md`, its
   bullets are pasted verbatim into the brief's Hazards section. No file,
   no section. Session-specific hazards the coordinator knows (a dirty
   file, a concurrent lander) are passed as an extra argument and appended.

## Emit this skeleton

Fill every `<...>`; drop a numbered step only when the brief's contract
says so (docs-only auto-ship drops TDD; a burndown builder stops after
commit instead of landing).

```
Implement <tracker ref> in <abs repo path> (origin <owner/repo>). Read the
ticket first, per that repo's tracker doc: full thread; the LATEST agent
brief is the contract.

Summary: <2-4 sentences: current behavior, desired behavior, scope edges
from the brief — pointer, not paraphrase, when the brief is good>.

Build steps (run directly; do not invoke /implement):
1. cd <repo>; fetch; verify clean checkout (stop and report if dirty).
2. git worktree add .claude/worktrees/<ticket-slug> -b <ticket-slug>
   origin/<default-branch>; work only there via absolute paths (verify
   .claude/worktrees/ is ignored; stop and report if not).
3. TDD on the ticket's named seams: failing test first, shown red, in the
   repo's existing test style; then implement to green. Seams: <from the
   brief; if the brief names none, the coordinator supplies them before
   dispatch>.
4. Run the repo's full test/check suite: <command from repo docs>.
5. Self-review the diff against each acceptance criterion.
6. Commit with body trailer `Closes <full cross-repo ref if the ticket
   lives outside the target repo, else #<n>>`.
7. <Land per the landing lane: `land` from inside the worktree (own repo)
   / stop after commit and report branch (burndown) / pushpr (foreign or
   PR-requested)>. Mechanical rebase conflict: resolve, retry once;
   logic conflict: stop and report.
8. Append a one-line milestone to <progress file path> after each step.

Hazards:
<verbatim bullets from docs/agents/hazards.md, then coordinator extras>

Report back: what changed, test results, <landed sha / branch name>, and
any deviation from the brief.
```

## Rules

- **Pointer over paraphrase.** The builder re-reads the ticket itself; the
  Summary orients, the brief is the contract.
- The coordinator announces the model pick (explore/build-to-pinned-spec →
  sonnet; subtle seams that pass review wrongly → opus) — the emitted brief
  never contains the model.
- Never include tracker CLI commands in the emitted brief beyond "per that
  repo's tracker doc" — the builder resolves them there.

## Prototype status

Throwaway. The question under test: does this skeleton + a hazards file
reproduce the hand-written briefs (5 real dispatches, 2026-08-31, all of
which landed)? Samples in `sample-126.md` and `sample-128.md` beside this
file. Verdict goes on second-brain-v2#130.
