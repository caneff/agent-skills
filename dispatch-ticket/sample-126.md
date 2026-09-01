# Sample: generated for second-brain-v2#126 (cross-repo, drills)

Coordinator extras supplied: target-repo override (brief said `sql-drills`,
which does not exist; Chris named `drills`); no hazards file in drills.

---

Implement caneff/second-brain-v2#126 in /home/caneff/src/drills (origin
caneff/drills). Read the ticket first, per that repo's tracker doc: full
thread; the LATEST agent brief is the contract. Note: the brief's target
"caneff/sql-drills" does not exist — caneff/drills is the drill repo; find
the SQL drill inside it, and stop and report if you cannot.

Summary: drill sessions improvise data-shape answers per problem and have
contradicted each other. Each problem gets a durable clarifications record
read-before-answer and appended-after-answer; the drill instructions state
the contract. Mostly convention + docs; engine code only if surfacing the
file requires it.

Build steps (run directly; do not invoke /implement):
1. cd /home/caneff/src/drills; fetch; verify clean checkout (stop and
   report if dirty).
2. git worktree add .claude/worktrees/fix-126 -b fix-126 origin/main; work
   only there via absolute paths (verify .claude/worktrees/ is ignored;
   stop and report if not).
3. TDD on the ticket's named seams: the clarifications-file convention and
   the instructions contract are docs — no test seam; if you touch engine
   code, failing test first in the existing .mjs style.
4. Run the repo's full test/check suite: npm test.
5. Self-review the diff against each acceptance criterion.
6. Commit with body trailer `Closes caneff/second-brain-v2#126`.
7. Finish: push the branch and open a PR for the owner to merge. Mechanical
   rebase conflict: resolve, retry once; logic conflict: stop and report.
8. Append a one-line milestone to
   /home/caneff/.claude/jobs/<job>/tmp/progress-126.md after each step.

Report back: what changed, where the convention lives, test results,
landed sha, and any deviation from the brief.
