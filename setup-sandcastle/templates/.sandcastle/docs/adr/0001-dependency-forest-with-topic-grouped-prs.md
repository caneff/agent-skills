# Dependency forest, with topic-grouped PRs

Status: accepted

## Context

A run was a single linear integration branch: every completed issue was folded
onto one tip, and the next iteration's branches were cut from that tip. This
fixed the intra-run deadlock (a dependent issue could finally pick up its
blocker's work mid-run) but welded two concerns together — *how issues are
built* (one ordered stack) and *how many PRs come out* (one, the stack). The
weld made it impossible to split a run into several topical PRs: two independent
dependency chains interleave in the stack (A,B,A,B), so no contiguous cut
separates them, and an issue cut from the global tip physically carries commits
it never needed.

## Decision

Un-weld the two concerns.

- **Build by dependency (the forest).** Each issue is based on its real parent
  branch (`sandcastle/issue-<parent>`), or `main` if it has none, or — for a
  multi-parent/diamond issue — a host-built temp branch merging all parents.
  Chains are independent off `main`; a child never carries an unrelated issue's
  commits. The integration tip and `foldLinear` are deleted. Parent branches are
  immutable once done, so there is no sibling-rebase and no per-issue git step
  after execute — only recording the parent edge.

- **Count PRs by topic (the grouping), chosen at the end.** The planner emits
  `parents: string[]` and a `group` key per issue. PRs are the connected
  components of `{parent edges} ∪ {same-group-key edges}` over this-run `done`
  issues. Each PR's head is the merge of its leaf tips into a throwaway merge
  head (single tip → that branch directly), based on `main`. The host computes
  groups, builds merge heads, and pushes; the consolidator agent only writes PR
  prose.

- **Run-scoped.** A run stacks only on work completed within it or already in
  `main`; cross-run dependencies wait for a human merge. A run iterates until
  the buildable backlog drains (raise the iteration cap rather than relying on a
  second run for completeness).

## Why this works / consequences

- A **dependency component is the atomic floor**: a child physically contains
  its parent, so grouping can only *combine* components, never split one. A
  parent edge that crosses two topic groups unions them automatically.
- Topic grouping moves from a **correctness** concern to a **presentation** one.
  In the linear stack a bad topic call broke the build or entangled the stack;
  in the forest, grouping is just "which independent tips to merge into a head,"
  so a bad call only yields oddly-grouped PRs — never a broken build or an
  un-revertable stack. This is the property that makes topical splitting viable
  at all.
- Group keys can drift across iterations (the planner reruns per iteration). The
  correctness-critical case is covered by the parent-edge union; remaining drift
  affects only independent same-topic issues split across iterations and is
  cosmetic. Mitigated by feeding prior group keys back to the planner for reuse.

## Considered and rejected

- **One PR per dependency component** (no topic layer): maximizes PR count — the
  finest granularity — which is the original tiny-PR pain the redesign exists to
  cure.
- **Cross-run stacking** (run N+1 bases on run N's unmerged branches):
  re-imports entanglement, merge-order coupling, and rewrite cascades across the
  run boundary, plus durable state a human can invalidate out-of-band. Rejected
  in favor of run-scoped + human-merge gate.
