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

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | Documented worker invocation interpolated the ticket body directly into a double-quoted shell string (`"<ticket body verbatim>"`), so a body containing `"`, backticks, or `$(` would run as shell instead of reading as text. |
