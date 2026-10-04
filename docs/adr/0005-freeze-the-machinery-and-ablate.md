# Freeze the burn and review machinery; change it by removal

Status: accepted (ruled by Chris 2026-10-04, "2 y")

## Context

77% of the 301 tickets filed 2026-09-20 to 10-04 target the burn, review and
implement tooling, which runs to about 5k lines of code, 8.8k of tests and
42k words of skill prose. Each friction point became a prevention ticket and
each ticket more machinery. Prior art (`docs/research/2026-10-04-agent-workflow-prior-art.md`)
changes a harness by removing one component at a time and measuring escapes.

## Decision

- No new tickets against the burn/review/implement machinery, except a bug
  that blocks work. Controller friction goes into one append-only friction
  log (`docs/agents/friction-log.md`), read at retro.
- For the next burns, one component at a time is switched off (candidates:
  the verification pass, Codex pass 2, one review axis); the review ledger
  counts bugs that escape to the seam or a later review. A component with no
  escapes is deleted.

## Consequences

The spec that carries ADR 0004's review shape also defines the escape count
and the ablation order.
