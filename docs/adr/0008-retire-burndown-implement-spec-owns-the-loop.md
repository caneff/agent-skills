# Retire burndown; implement-spec owns the dispatch loop

Status: accepted (ruled by Chris 2026-11-03, the #1634 grilling: rulings 1 to 8)

## Context

`drain` replaced the burn for everyday use on 2026-10-04 (#1403), and the last
session with a typed `/burndown` was last modified 2026-10-06. The command
could not simply be deleted, because spec runs ran on its dispatch loop and
modules: `implement-spec` described itself as policy over that loop. An agent
reading the tree had to work out that a dead command's directory was the spec
run's engine.

The burn (#776, #885) solved draining a mixed queue in parallel, with clumping
to keep two workers out of one file. `drain` runs one bundle at a time, so that
collision cannot happen. The cost is speed on a queue of independent tickets,
which Chris accepted on 2026-10-04. A spec run's slices stay parallel, guarded
by blocked-by edges and the hold on files in flight.

## Decision

There is no more burn. `/burndown` and `burndown/` are gone. `implement-spec`
owns the dispatch loop, its modules and its prose, in one `SKILL.md`. Unrelated
tickets go through `drain` only, and parallel work exists only inside a spec
run. A spec run's dispatcher is a session or `drain`, and its `--slots` are its
own, bounded by the box rule.

This outranks two rules of ADR 0005, by Chris's rulings of 2026-11-03 on #1634:

- **One component at a time.** ADR 0005 switches off one component and measures
  escapes before deleting it. This retirement removes several parts at once
  with no ablation: the command, its handoff, the slot debit, `tier.py` and
  `closure.py`'s grouping.
- **No new tickets against the machinery.** #1634 and its slices are such
  tickets. They are a removal, the kind of change ADR 0005 allows, and they were
  ordered by Chris directly.

The friction log and the review ledger of ADR 0005 stand unchanged.

## Consequences

- The change reaches the default branch in one merge, while no drain or spec
  run is alive (`implement-spec/retire_landing.py`).
- A queue of independent tickets drains serially. Getting parallel work means
  writing a spec.
- A spec run's dispatcher can no longer budget a run's slots against its own.
  The box check before every dispatch is the only cross-run bound.
- `clump` stays in code and in the run file (ruling 5), defined in `GLOSSARY.md`
  as one slice's slot in a run.
- Whether a model follows the merged `SKILL.md` is checked by the first real
  spec run after landing, not by any suite.
