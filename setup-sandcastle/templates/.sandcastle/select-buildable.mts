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

export function selectBuildable(
  openIssues: OpenIssue[],
  blockedByEdges: Map<number, number[]>
): OpenIssue[] {
  const open = new Set(openIssues.map((i) => i.number));
  return openIssues.filter((issue) =>
    (blockedByEdges.get(issue.number) ?? []).every(
      (blocker) => !open.has(blocker)
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
  requireLabel = "ready-for-agent"
): OpenIssue[] {
  return selectBuildable(openIssues, blockedByEdges).filter((issue) =>
    issue.labels.includes(requireLabel)
  );
}
