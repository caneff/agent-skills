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

## Review shape (ruled by Chris 2026-10-04, "1 y")

One review wave: the three axes, plus Codex when #1357's size gate admits
it, run in parallel; the worker fixes every finding; the seam (`bash
tests/all.sh`) is the convergence check. No verification re-review, no
second Codex pass. Evidence: `docs/research/2026-10-04-agent-workflow-prior-art.md`
(single-pass review beats multi-turn; the ledger's Codex pass 2 scored 3 in
value over 70 runs). The skill changes land as one spec after burn
burn-skills-2026-10-03 closes.
