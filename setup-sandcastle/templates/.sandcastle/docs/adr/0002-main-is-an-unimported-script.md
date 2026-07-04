# `main.mts` is a never-imported orchestration script

Status: accepted

## Context

`main.mts` is ~980 lines: a linear plan→execute→review→PR pipeline (Phases 0–3)
plus ~280 lines of helper functions, all in one file. Side effects fire at
import — label creation, worktree GC, the whole run. A recurring instinct (human
or agent) is to "decompose" it: split into `host-io` / `sweep` / `execute` /
`pr-heads` modules, or hide the script body behind a `main()` guard with the
helpers exported, so the pieces become individually importable and testable.

Three facts make that instinct wrong here:

1. **Nothing imports `main.mts`.** It is only ever run as a script
   (`npx tsx .sandcastle/main.mts`). The only things that ever referenced it
   were grep-the-source tests (`readFileSync(main.mts)` + regex), which are
   deleted. With those gone, there is no importer to trip over the import-time
   side effects — and those side effects are exactly what running the script
   _should_ do.

2. **The phase pipeline is one linear flow over shared mutable state**
   (`git`, `hooks`, `prAssignments`, `allCompleted`, `runId`). Splitting it into
   files turns that shared state into wide DI interfaces passed between shallow
   modules — _more_ surface to track across files, not less. A linear pipeline
   read top-to-bottom in one file is high-locality; shattering it trades that
   locality for nothing. (See `codebase-design`: depth/locality, not line count,
   is the metric.)

3. **The genuinely testable logic is not phase orchestration** — it is small
   pure decisions (verdict parsing, in-review routing, sandbox config). Those
   belong in pure modules that are _already_ importable, not exposed via a seam
   bolted onto `main.mts`.

## Decision

`main.mts` stays a single, never-imported orchestration script. We do **not**
add a `main()` guard, do **not** export its helpers, and do **not** split it
into modules. Line count alone never justifies the change.

When a piece of `main.mts` needs a test, **extract that piece to a pure module**
(its thematic home — `reconcile.mts`, `sandbox-identity.mts`,
`base-resolution.mts`, …) as a pure function (plain data in, plain data out, or
the existing `{git, …}` dependency-injection convention), and test it there.
`main.mts` calls the extracted function. This deepens the pure module and keeps
`main.mts` a thin caller — the opposite of exposing `main.mts` internals through
a seam.

Tests assert against these pure modules, never by reading `main.mts` source.
Grep-the-source "contract" tests are banned: they pass on broken wiring and
break on reformatting.

## Consequences

- `main.mts` remains long, and that is fine — it is a linear script, not a
  library.
- Wiring that only exists inside `main.mts` (e.g. "this phase runs before that
  one") is verified by integration runs, not unit tests. Where a wiring
  invariant is high-stakes (bot identity reaching every sandbox), introduce a
  single chokepoint in a pure module that every call site must route through,
  and test the chokepoint — do not regex `main.mts`.
