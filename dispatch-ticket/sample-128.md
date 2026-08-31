# Sample: generated for second-brain-v2#128 (agent-skills, hazards in play)

Coordinator extras supplied: two session hazards (a fresh commit touching
the same file; concurrent landers). agent-skills has no
docs/agents/hazards.md yet — the two standing hazards below are the kind
that file would hold.

---

Implement caneff/second-brain-v2#128 in /home/caneff/.agents/skills
(origin caneff/agent-skills). Read the ticket first, per that repo's
tracker doc: full thread; the LATEST agent brief is the contract.

Summary: the code-review skill scopes its diff against the local default
branch, which is stale in long-lived worktrees, so already-merged commits
produce false findings. Change the diff-scoping instructions to fetch,
discover the remote default branch (never hard-code main), and scope
against fresh origin/<default>, with an explicit fallback notice on fetch
failure. Instructions-only change; no engine code.

Build steps (run directly; do not invoke /implement):
1. cd /home/caneff/.agents/skills; fetch; verify clean checkout (stop and
   report if dirty).
2. git worktree add .claude/worktrees/fix-128 -b fix-128 origin/main; work
   only there via absolute paths (verify .claude/worktrees/ is ignored;
   stop and report if not).
3. TDD on the ticket's named seams: prose instructions — no test seam;
   your check is re-reading the modified section against each acceptance
   criterion.
4. Run the repo's full test/check suite: markdown format check if
   configured; none otherwise.
5. Self-review the diff against each acceptance criterion.
6. Commit with body trailer `Closes caneff/second-brain-v2#128`.
7. Land: from inside the worktree run `land`. Mechanical rebase conflict:
   resolve, retry once; logic conflict: stop and report.
8. Append a one-line milestone to
   /home/caneff/.claude/jobs/<job>/tmp/progress-128.md after each step.

Hazards:
- The hooks under flow/claude/hooks/ are live in every running session via
  ~/.claude/hooks symlinks — edit only worktree copies, never the primary
  checkout.
- Other agents may land on this repo's main concurrently — branch after a
  fresh fetch; a land conflict usually clears on one fetch-and-retry.
- Session extra: main just received a commit touching code-review/SKILL.md
  (report-routing paragraph) — branch from origin/main after fetching so
  you include it; your change is a different section of the same file.

Report back: what changed, the exact new command sequence the skill
prescribes, test results, landed sha, and any deviation from the brief.
