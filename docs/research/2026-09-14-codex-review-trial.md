# Codex adversarial-review trial (#812)

Chris ruled a trial, not a permanent rule (2026-09-14): does a Codex
adversarial pass find real problems the three Claude review axes miss? Chris
ruled again (2026-09-15, #817) to move the pass off the worker it
reviews — independence needs the builder out of the loop — to the
controller, at merge time. The procedure the controller follows lives in
`implement/SKILL.md` § The merge step 3; this note doesn't restate it.

One row is appended here per heavy Claude-lane ticket that ran the pass (a
skipped pass adds no row), as an auto-ship commit on `main` after the
merge, counted as rows land rather than as PRs are drafted. The trial ends
after five rows: the controller whose row brings the count to five brings
Chris this table plus a keep/drop recommendation — keep if at least one
`codex-only, confirmed` finding would have shipped a real bug, drop if the
pass only repeated the Claude axes or raised noise.

The #814 row was classified by the builder (pre-#817 rule); from #817 on, rows are classified by the controller against the PR body's full round-1 list.

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | Documented worker invocation interpolated the ticket body directly into a double-quoted shell string (`"<ticket body verbatim>"`), so a body containing `"`, backticks, or `$(` would run as shell instead of reading as text. |
| #817 | #818 | 3 | 0 | 0 | Run 1 [high]: the PR body listed only disputed/filed round-1 findings, so a fixed Claude finding vanished and a matching Codex finding would be miscounted as codex-only. Run 1 [medium]: the controller invocation printed to stdout with no file bound, so no raw-output record existed to post. Run 2 [high]: the pass left its output and ticket-body files in `.scratch/`, so `merge-cleanup` (which refuses ignored `.scratch/` content without `--discard`) would stall after every pass. |
| #822 | #827 | 1 | 1 | 1 | Run 2 [high]: the `PRE_REPORT_KEEP_SCRATCH` escape hatch passes the gate but no PR-up field or controller check carries its reason, so kept `.scratch/` surfaces only when `merge-cleanup` refuses (filed #831; fail-safe, a visibility gap rather than a shipped bug). Also found by Claude: run 1's unreadable-`.scratch/` false pass, raised by the Correctness axis and disputed by the worker, fixed after Codex raised it. Disputed: run 2's still-running-writer refill (cleanup fails closed). |
| #821 | #829 | 3 | 0 | 0 | Run 1 [high]: the claim-clearing `gh issue edit` result was discarded, so cleanup reported success after a failed edit with the branch already gone (fixed, re-run command printed). Run 1 [medium]: `--remove-assignee @me` cleared only the runner, not the issue's real assignees (fixed; in this lane dispatch claims as the same login, so it bites only on a reassigned ticket). Run 2 [high]: that failure path still exits 0 (filed into #823). |
| #819 | #830 | 2 | 0 | 0 | Run 1 [high]: the session lookup took the first live registry record in the worktree by filename order, not the one matching the dispatched herdr agent's `agent_session.value`, so a second session in the worktree printed the wrong name (fixed, sessionId match plus a two-session witness test). Run 2 [medium]: the lookup gives up after ~100 ms, so a late SessionStart hook prints `(unavailable)` under load (filed #836). |
