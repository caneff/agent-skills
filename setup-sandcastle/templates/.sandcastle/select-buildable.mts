// The deterministic frontier filter.
//
// Given the open issues and their native GitHub `blockedBy` edges, return the
// buildable set: the open issues whose every blocker has already closed. A
// blocker still counts only while it is itself open — i.e. still present in the
// open-issue set. Merging a blocker's PR closes its issue, drops it out of that
// set, and only then does a dependent's blocker count fall to zero. So a child
// whose parent issue is still open is never buildable; this is the whole of the
// parent-merged-to-main rule expressed as a pure function.
//
// Pure and content-blind: it reasons only over ids and edges, never GitHub, so
// it is unit-testable with injected fixtures. The Phase 1 opus planner consumes
// this set and prunes it further for implicit same-file conflicts.

import type { OpenIssue } from "./reconcile.mts";

// `satisfiedThisRun` holds ids of parents that built AND passed review this run
// (the in-memory run-scoped built-set). A blocker in it counts as satisfied even
// while its issue is still open, so a child advances to the next chain level
// within one run. Empty or absent, selection is exactly the closed-blockers rule
// above — the whole point of this argument's default.
export function selectBuildable(
  openIssues: OpenIssue[],
  blockedByEdges: Map<number, number[]>,
  satisfiedThisRun: Set<number> = new Set()
): OpenIssue[] {
  const open = new Set(openIssues.map((i) => i.number));
  return openIssues.filter((issue) =>
    (blockedByEdges.get(issue.number) ?? []).every(
      (blocker) => !open.has(blocker) || satisfiedThisRun.has(blocker)
    )
  );
}

// The whole rule the planner is handed: buildable AND carrying the lifecycle
// label that marks an issue plannable. selectBuildable answers "unblocked";
// this adds "and labeled", so both halves of the frontier contract live in one
// tested place instead of the label half leaking to the caller as an inline
// filter. Buildability wins over the label — a labeled but still-blocked issue
// is not selectable.
export function selectableFrontier(
  openIssues: OpenIssue[],
  blockedByEdges: Map<number, number[]>,
  requireLabel = "ready-for-agent",
  satisfiedThisRun: Set<number> = new Set()
): OpenIssue[] {
  return selectBuildable(openIssues, blockedByEdges, satisfiedThisRun).filter(
    (issue) => issue.labels.includes(requireLabel)
  );
}

// The replan loop's per-iteration work decision (#342). It is `selectableFrontier`
// — buildable ∩ labeled, treating parents built this run as satisfied — minus
// every issue already attempted this run. `attemptedThisRun` is the broader
// "offered this run" set (built, review-failed, errored, or planner-pruned); it
// guarantees progress and termination: an issue is offered at most once, so the
// loop only gains new work when a built parent unblocks a child, and an empty
// return is the fixpoint that ends the run. `satisfiedThisRun` is the narrower
// built-AND-reviewed set that unblocks children; it is normally a subset of
// `attemptedThisRun`.
export function nextBuildable(
  openIssues: OpenIssue[],
  blockedByEdges: Map<number, number[]>,
  satisfiedThisRun: Set<number>,
  attemptedThisRun: Set<number>,
  requireLabel = "ready-for-agent"
): OpenIssue[] {
  // In-run advancement stacks SINGLE-parent chains only (#342). A child with two
  // or more parents is a diamond: it keeps today's behavior (spec #340 story 11)
  // — it waits until ALL its parents have actually closed (merged to `main`), and
  // never builds while a parent has merely built this run. `resolveBase` sends a
  // diamond to `main`, so building it before its parents merge would put it on a
  // base missing that unmerged parent's code. "Closed" = absent from the open set.
  const open = new Set(openIssues.map((i) => i.number));
  const diamondWaiting = (issue: OpenIssue): boolean => {
    const blockers = blockedByEdges.get(issue.number) ?? [];
    return blockers.length > 1 && blockers.some((b) => open.has(b));
  };
  return selectableFrontier(
    openIssues,
    blockedByEdges,
    requireLabel,
    satisfiedThisRun
  ).filter(
    (issue) => !attemptedThisRun.has(issue.number) && !diamondWaiting(issue)
  );
}
