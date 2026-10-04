# Workers fix their own review findings

Status: accepted (ruled by Chris 2026-10-04: "they should fix their own stuff, not drop valid things on the floor")

## Context

Spec #1024 sent every finding over its adjacent-fix size bar (one function,
one file in the diff, under 20 lines) to a leftover, filed at run close as a
sweep ticket. Sweeps roll over: #1353 held 49 leftovers and its worker, with
none of the original context, fixed 1 (PR #1376) and re-recorded 48. A first
draft of this ADR (ba83592, reverted in 757ae15) dropped leftovers instead;
Chris rejected that, since the findings are valid.

## Decision

The worker whose PR a review covers fixes every valid finding in that PR.
No size bar. A valid finding is never dropped. Only a finding that needs a
design of its own leaves the PR, added to the open ticket for its component
(or filed, if none exists) under the search-before-filing rule in `CLAUDE.md`.

## Open

How to hold review rounds down while every finding is fixed in the PR:
proposed to Chris 2026-10-04, not yet ruled. The skill changes this ruling
needs (the adjacent-fix bar and `leftover` outcome in `implement/SKILL.md`)
wait on that answer, so they land as one change.
