# Context — Sandcastle orchestrator

Glossary for the `.sandcastle/` dev-automation orchestrator that builds issues
into PRs. Terms only — no implementation details, no decisions (those live in
`docs/adr/`). Distinct from the repo-root `CONTEXT.md`, which describes the
target project this orchestrator builds.

## Glossary

**Run** — One invocation of the orchestrator (`main.mts`). Loops plan→execute
over iterations until the buildable backlog drains or the iteration cap is hit.
Produces a set of PRs.

**Iteration** — One plan→execute cycle inside a run. The planner selects the
issues unblocked _right now_; later iterations pick up issues whose blockers
completed in earlier iterations of the same run.

**Issue branch** — `sandcastle/issue-<id>`. Holds one issue's commits, cut from
its resolved base (its parent's branch, or `main`).

**Parent** — An issue another issue builds on, emitted by the planner as
`parents: string[]`. At build time a parent is always either completed _this
run_ (its issue branch exists) or already in `main` (earlier run, merged).
_Avoid_: blocker (a blocker is unbuilt; a parent is built and depended on).

**Chain** — A linear sequence of issues linked parent→child off a single root
(e.g. `112 → 108`).

**Root** — A parentless issue; its base is `main`. The start of a chain.

**Forest** — The whole run's set of issue branches, structured as independent
chains off `main` rather than one linear stack. Replaces the former single
integration tip.
_Avoid_: integration tip, run branch, stack (the old single-tip model).

**Component** — A connected piece of the run's dependency forest (issues linked
by parent edges, transitively). The **atomic floor** of PR grouping: because a
child branch physically contains its parent's commits, a component can never be
split across PRs — only combined with others. May fork (one parent, several
children) or join (diamond).

**Topic group** — A set of issues the planner tags with the same `group` key
because they belong to the same feature/theme, even when no dependency links
them. The grouping signal for PRs. Topic combines independent components; it can
never split a component (parent edges win).

**PR set** — One connected component of the graph whose edges are
`{parent edges} ∪ {same-group-key edges}`, over the issues completed this run.
Becomes exactly one PR. Its **head** is the merge of its leaf tips (issues no
other issue in the set builds on): a single tip is the head directly; multiple
tips are merged into a throwaway **merge head** branch. Base is always `main`.

**Run-scoped** — A run stacks only on work completed _within that run_ or
already in `main`. It does not adopt another run's unmerged work as a parent;
cross-run dependencies wait for a human merge.

**Human-gated** — An open issue whose next move is a human's, so a run
leaving it untouched is correct: an open PR pending merge, `ready-for-human`,
or untriaged. Opposite: buildable (ready-for-agent) or stranded.

**Untriaged** — An open issue with no lifecycle label. Invisible to the
planner by design; reported in the bucketed run summary, not silently skipped.

**Stranded** — An issue labeled `in-review` for which no open PR exists (a
run crashed between eager labeling and lazy PR creation). The label lies.
Distinguished from a human veto by the absence of any closed-unmerged PR
referencing it; from genuinely human-gated by the absence of any open PR.

**Reconciliation sweep** — A start-of-run pass restoring the `in-review ⟺
open PR` invariant. For each `in-review` issue: open PR → leave untouched;
closed-unmerged PR → relabel `ready-for-human`; no PR + branch with work →
inject into the run's completed set for Phase 3 to open its PR; no PR + no
branch → relabel `ready-for-agent`.
