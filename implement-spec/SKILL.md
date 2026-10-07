---
name: implement-spec
description: "Drive one sliced spec as a nested run — the burn's worker, its own slices' controller, with an exploration pass, an integration branch its slices land on, one spec-level review and fix round, and one integration PR to the default branch."
disable-model-invocation: true
---

One spec's slices, driven as one run. A mixed-origin queue — several tickets
from different specs — is [`burndown`](../burndown/SKILL.md)'s job.

## The loop is not here

Picking the next clump, starting it, waiting, refilling as slots free, the
box reading before each dispatch, clumping, the frontier and the run file:
all of that is [`burndown/SKILL.md`](../burndown/SKILL.md) § The loop, which
is its single home. Read it there and run it as written. This file is
**policy over that loop**, and states only the five things a spec run does
differently: the nesting, the exploration pass, the integration branch, the
closing check, and the spec-level review. Anything it does not override, the
loop decides.

## The nesting

A spec run is a **worker to the burn** that dispatched it and a **controller
to its own slices**. Both at once, and neither half is metaphorical: it
reports to the burn's controller the way any worker does, escalates and parks
by that controller's rules, and it dispatches, rules on and merges its slices
the way any controller does. What a controller rules on is
`implement/SKILL.md` § Control, and the merge is that file's § The merge.

Its slots are **debited from the dispatching burn's budget**, not added
beside it. One budget, one box: a nested run that counted its own slots
separately would double-spend the machine the box reading is there to
protect, and the burn holding the budget is the one that can see both halves.
A spec run that wants more slots asks the burn for them.

## The exploration pass

One pass over the spec, before any slice is dispatched: what the spec's
decisions say, and what the code already does about each one. Its output is a
**summary** — one line per decision — plus whatever must reach Chris.

What reaches him is read by
[`contradictions.py`](contradictions.py), not by eye:

```
python3 implement-spec/contradictions.py <exploration.json>
```

The check compares a decision the code does not implement against **the
spec's own ticket list first**. A decision a ticket of this spec builds is
**not yet built** — a summary line naming that ticket, never a ruling for
Chris. Only "the code does this, **differently**" escalates as a
contradiction. A decision the code has never heard of, that no slice builds,
is a summary line too: a gap in the slicing, for the controller to close by
filing, not drift for Chris to rule on.

Which of those two a decision is — the code has not got there yet, or the
code does it another way — is the pass's own reading, and the line between
them is drawn in the reference. Where both readings honestly fit, it is the
first: the channel that reaches Chris is the one that has to stay clean.

The three verdicts, that boundary, the input the reader takes, and the run
this rule came from: [`references/exploration.md`](references/exploration.md).

## The integration branch

A spec with more than one slice is built on its **integration branch**,
`spec-<n>`, and reaches the default branch in one PR (#1457, rulings 1a, 2a,
4y, 5y; ADR 0006). `implement-dispatch --spec <n>` pushes `spec-<n>` off
`origin/<default>`, or reuses an `origin/spec-<n>` already there, and this
run's own workspace is on it. Each slice is dispatched onto it: its workspace
branches from `origin/spec-<n>`, and it builds with TDD, its narrowed seam and
the pre-report gate but no review wave (`implement/SKILL.md` § Review). This
run merges each slice PR into `spec-<n>` by `implement/SKILL.md` § The merge
with its slice substitutions; a slice ticket stays open until the
integration PR closes it.

When the last slice has landed:

1. **Keep current.** In this workspace, take in the slices first: they
   merged into `origin/spec-<n>` on GitHub, and the local `spec-<n>` stays
   where dispatch cut it until it does. Then merge `origin/<default>` in and
   push: `git fetch origin && git merge --ff-only origin/spec-<n> && git
   merge --no-edit origin/<default> && git push origin spec-<n>`, the block
   the closing check carries. Never a rebase: it rewrites the shas the
   dispositions name. A conflict is the fix round's first job.
2. **One review.** Run the spec-level review (§ The spec-level review).
3. **One fix round.** This run is the spec's one fix worker, in its own
   workspace on `spec-<n>`: git refuses a second checkout of a branch a
   workspace already holds. It follows steps 2–3 of
   `implement/SKILL.md` § Review, with the spec number for `<n>`: every finding gets one disposition in
   `dispositions-<spec>.jsonl`, and the full seam runs, `bash tests/all.sh`
   from a tree with `origin/<default>` merged in again. The pre-report gate
   runs the merge check on `spec-<n>` keyed on the spec number, so
   `fix-check.sh <spec> spec-<spec>` must exit 0 before the PR goes up.
4. **The integration PR.** Run step 1's block once more, and open it:
   `gh pr create --base <default> --head spec-<n>`. Its body is
   `implement/SKILL.md` § The PR's, keyed on the spec number, with a bare
   `Closes #<slice>` line for every slice and a bare `Closes #<spec>`.
   Report it to this run's own controller as "PR up" in that section's
   shape, with `fix-check.sh <spec> origin/spec-<spec>` as the controller's
   merge check. The controller merges it unchanged by
   `implement/SKILL.md` § The merge, with step 5's check that each `Closes`
   issue closed; a `ready-for-human` spec hands Chris the merge line.

A one-slice spec gets no integration branch (ruling 3a): its slice branches
from and lands on the default branch with its own review wave, as a lone
ticket does.

## The closing check

The spec has no ticket of its own for it. Once the last slice has landed on
`spec-<n>`, this run generates the closing-check section for the integration
PR with [`closing_ticket.py`](closing_ticket.py) and posts it as a comment on
the spec issue (`gh issue comment <spec> --body-file`), so the review and the
fix round read it with the spec. The end-to-end test runs there, at the seam
on `spec-<n>` merged with current `<default>`. A one-slice spec has no
integration PR: `--one-slice` makes a section for that slice's body, appended
before it is dispatched (`gh issue edit`), with no spec-level review, since
the slice's own review wave is the review. The generator refuses to omit two
things a worker left to write the section on its own would otherwise have to
invent:

```
python3 implement-spec/closing_ticket.py <repo-root> <spec> --surface <what> [--surface <what>]...
python3 implement-spec/closing_ticket.py <repo-root> <spec> --no-surface
python3 implement-spec/closing_ticket.py <repo-root> <spec> --one-slice --no-surface   # one-slice spec
```

`<default>` is read off the repo's `origin/HEAD`, or given with `--default`;
the generator refuses rather than assume `main`.

- It names the repo's **end-to-end seam** and **what that seam is blind
  to** — from the repo's `## End-to-end seam` declaration, which outranks
  the exploration pass; the pass fills only what the declaration omits, and
  where both are present and differ the generator refuses and names both. A
  seam with no stated blind spot is refused too: a green run at a seam that
  has drifted from the shipping surface is the failure this names.
- Where the spec has a **user-visible surface the seam cannot reach**, the
  section says so, and its acceptance carries **one open of the real thing**
  for each — checked in the shipping surface, not in the seam.

The declaration grammar and the evidence:
[`references/closing-ticket.md`](references/closing-ticket.md).

## The spec-level review

One wave, after the last slice lands and `origin/<default>` is merged in,
over `origin/<default>...spec-<n>` from this run's workspace on `spec-<n>`:
the three axes of `/multi-axis-code-review origin/<default>` and one Codex
pass behind `codex-usage-gate.py`, which still answers the kill switch, the
reserve ceiling and the size threshold (`implement/SKILL.md` § The Codex
pass). The integration branch holds this spec's slices and merges of
`<default>`, nothing else, so the range is the review's own; the merge-sha
list and the cherry-picked comparison a spec landing slice by slice needed
are gone.

The ticket text the review judges against is the spec and every slice,
bodies and comments, each rendered as `implement/SKILL.md` § The brief
renders a ticket. The findings sidecars, the Codex record, the review-ledger
rows and `dispositions-<spec>.jsonl` are all keyed on the spec number, so
the escape count attributes a later bug to the review that missed it. The
slices recorded no review rows at all, not skip rows.
