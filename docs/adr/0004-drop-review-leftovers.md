# Drop review leftovers; no sweep tickets

Status: accepted (ruled by Chris 2026-10-04: "if it isn't worth fixing it will never get fixed")

## Context

Spec #1024 (2026-09-23) made every review finding a PR did not fix a
**leftover**, recorded in the run file and filed at run close as one sweep
ticket per burn. Sweeps do not clear leftovers: #1353, the sweep for burn
burn-skills-2026-10-02b, held 49 items and its worker fixed 1 (PR #1376) and
re-recorded 48. A leftover is a finding the worker and the verifier already
judged not worth fixing in the PR; a third agent rarely disagrees. The review
ledger baseline (`docs/research/2026-09-30-review-ledger-baseline.md`) shows
most axis findings are fixed in-PR (leftover rates 8-17%), so the leftovers
are the residue, not the bulk. Prior art agrees: no reviewer system found
turns unfixed findings into tickets, and Google's reviewer guide says
deferred cleanup "usually... never happens"
(`docs/research/2026-10-04-agent-ticket-inflation.md`).

## Decision

A review finding is fixed in the PR or dropped. Nothing records it for later:
no `leftover` outcome, no run-file leftovers, no per-burn or per-PR sweep
ticket. A finding that is a real defect and too big for the PR is filed as
its own ticket under the search-before-filing rule in `CLAUDE.md`, the same
as any other ticket.

## Consequences

- Until the machinery is removed (#1399), a worker or controller does not
  file a sweep ticket or run `runfile.py leftover`; the PR body's
  disposition lines still name what was dropped, as the record.
- The leftover and sweep code (`runfile.py leftover`, `sweep.py render`,
  `sweep.py blocked-by`, the sweep sections of `burndown/SKILL.md` and
  `implement/SKILL.md`) is removed in #1399. `sweep.py counts` reports two
  counts, fixed in-round and filed.
