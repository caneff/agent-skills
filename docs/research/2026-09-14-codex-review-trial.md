# Codex adversarial-review trial (#812)

Chris ruled a trial, not a permanent rule (2026-09-14): does a Codex
adversarial pass find real problems the three Claude review axes miss? On
heavy Claude-lane builds, round 1 of review now also runs
`/codex:adversarial-review` on the diff, handed the ticket body verbatim,
alongside the three `/multi-axis-code-review` axes. The pass never blocks a
build — a worker not logged in to Codex, or hitting an error, skips it and
says so in the PR body.

One row is appended here per heavy Claude-lane ticket that ran the pass
(a skipped pass adds no row). The trial ends after five rows: the worker
whose PR adds the fifth says "codex trial complete" in "PR up", and the
controller brings Chris this table plus a keep/drop recommendation — keep if
at least one `codex-only, confirmed` finding would have shipped a real bug,
drop if the pass only repeated the Claude axes or raised noise.

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | Documented worker invocation interpolated the ticket body directly into a double-quoted shell string (`"<ticket body verbatim>"`), so a body containing `"`, backticks, or `$(` would run as shell instead of reading as text. |
