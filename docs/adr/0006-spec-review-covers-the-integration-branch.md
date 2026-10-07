# A spec run's review covers its integration branch, and one fix worker disposes of every finding

Status: accepted (ruled by Chris 2026-10-06, the #1457 grilling: rulings 1a, 2a, 3a, 4y, 5y)

## Context

Since #1452, `/to-tickets` slices a spec into tracer bullets sized for one
worker, so a spec yields more and smaller slices. Under ADR 0004 each slice
ran its own review wave, three axes and a Codex pass, and landed on the
default branch alone: the review cost scaled with the slice count, each slice
was reviewed without the rest of the spec in view, and the default branch
held a half-built spec between landings. The spec-level review could not read
a clean range on the shared default branch either, so the closing check
rebuilt one by cherry-picking a list of merge shas.

## Decision

A spec with more than one slice is built on an **integration branch**,
`spec-<n>`, cut from the default branch. Its slices land there and run no
review wave of their own. When the last slice has landed, the default branch
is merged in (never rebased), and one wave, the three axes and one Codex pass,
reviews `origin/<default>...spec-<n>` against the spec and every slice. One
fix worker, not the slices' authors, disposes of every finding as ADR 0004
requires and runs the full seam. One PR takes `spec-<n>` to the default
branch and closes every slice and the spec.

This supersedes ADR 0004's "the worker whose PR a review covers fixes every
valid finding in that PR" for spec runs only: the review covers the
integration branch, and the fix worker is the one whose PR, the integration
PR, it covers. ADR 0004's no-drop rule and its one-wave shape stand
unchanged.

A lone ticket, and the slice of a one-slice spec, keep ADR 0004's per-ticket
wave and land on the default branch as before (ruling 3a).

## Consequences

- The fix worker is the spec run itself, in its own workspace on
  `spec-<n>`: git refuses a second checkout of a branch a workspace holds.
  The pre-report gate runs the merge check on `spec-<n>`, and the merge
  check, findings sidecars, Codex record, dispositions and ledger rows are
  keyed on the spec number.
- A finding the review raises in code an earlier slice wrote is fixed on the
  integration branch by the fix worker, not sent back to that slice's
  author, whose workspace is gone.
- Per-slice review waves are removed, which ADR 0005 records as a removal.
