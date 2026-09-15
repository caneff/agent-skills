# Codex adversarial-review trial (#812)

Chris ruled a trial, not a permanent rule (2026-09-14): does a Codex
adversarial pass find real problems the three Claude review axes miss? Chris
ruled again (2026-09-15, #817) to move the pass off the worker it reviews:
independence needs the builder out of the loop. On a heavy Claude-lane PR,
the controller runs `/codex:adversarial-review` on the diff — handed the
ticket body verbatim — at merge time, after the PR is confirmed not-draft
and CLEAN and before the merge itself. The pass never blocks a build — a
controller not logged in to Codex, with no plugin entry, or hitting an
error, skips it and comments "Codex pass skipped: `<why>`" on the PR instead.

When the pass runs, the controller posts its raw output as a PR comment
before acting on it. No material findings → merge as normal. Findings → the
controller holds the merge, sends the worker the findings and the comment
URL, and the worker disposes of each one (fixed in a commit /
`disputed: <why>` / filed) and sends "PR up" again; the controller re-runs
the pass once on the fixes — there is no third run — then merges.

One row is appended here per heavy Claude-lane ticket that ran the pass
(a skipped pass adds no row), as an auto-ship commit on `main` after the
merge. The controller classifies each finding by comparing it with the PR
body's round-1 findings and counts the rows as they land on `main`. The
trial ends after five rows: the controller whose merge adds the fifth
brings Chris this table plus a keep/drop recommendation — keep if at least
one `codex-only, confirmed` finding would have shipped a real bug, drop if
the pass only repeated the Claude axes or raised noise.

| Ticket | PR | codex-only, confirmed | also found by Claude | disputed | codex-only confirmed findings |
|---|---|---|---|---|---|
| #814 | #816 | 1 | 2 | 1 | Documented worker invocation interpolated the ticket body directly into a double-quoted shell string (`"<ticket body verbatim>"`), so a body containing `"`, backticks, or `$(` would run as shell instead of reading as text. |
