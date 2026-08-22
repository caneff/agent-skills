// How a run's built issues map to pull requests.
//
// The default is one PR per issue (`issue` mode) — the historical behavior. In
// `spec` mode a whole spec lands as ONE PR: the built issues that share a native
// GitHub sub-issue parent (the spec) collapse into a single group. A run stacks
// a linear spec level by level, so the group's tip branch already contains the
// whole spec — `chooseTip` finds it, and the caller opens one PR from that tip.
// An issue with no parent (a standalone ticket) is its own group of one, so spec
// mode degrades to issue mode for anything ungrouped.
//
// Pure and IO-blind: both functions reason only over ids, the parent edge, and
// an injected ancestry predicate — never git or GitHub — so they are unit-
// testable with plain fixtures. The caller owns the push/PR IO around each group.

// A built-AND-reviewed issue, in build order. `parent` is the issue's native
// GitHub sub-issue parent — the spec — or null for a standalone ticket.
export interface BuiltIssue {
  id: number;
  branch: string;
  parent: number | null;
}

// One pull request's worth of built issues. `key` is the parent number in spec
// mode (the issue's own id for an orphan or in issue mode); `members` are the
// issues on that PR, in build order.
export interface PrGroup {
  key: number;
  members: BuiltIssue[];
}

export type PrGrouping = "issue" | "spec";

// The one member of a spec group whose branch contains every other member's —
// the tip of a stack. A run stacks a linear spec level by level (each ticket's
// branch is cut from its just-built blocker's branch), so the last ticket's
// branch already holds the whole spec: opening ONE PR from that tip is one PR
// per spec, no merge needed. Returns null when no single branch contains all
// the others — a flat spec (independent siblings) or a diamond — so the caller
// falls back to one PR per issue.
//
// Pure and git-blind: `isAncestor(a, b)` — is branch `a` an ancestor of branch
// `b` — is injected, so this is unit-testable without a repo. A lone member is
// its own tip and never consults ancestry.
export function chooseTip<T extends { branch: string }>(
  members: T[],
  isAncestor: (ancestorBranch: string, descendantBranch: string) => boolean
): T | null {
  return (
    members.find((candidate) =>
      members.every(
        (other) =>
          other === candidate || isAncestor(other.branch, candidate.branch)
      )
    ) ?? null
  );
}

// Group built issues into pull requests. `issue` mode returns one singleton
// group per issue, in build order. `spec` mode groups by `parent ?? id`, so
// siblings under a spec collapse and orphans stay solo; members keep build
// order and groups keep first-seen order.
export function prGroups(built: BuiltIssue[], mode: PrGrouping): PrGroup[] {
  const groups: PrGroup[] = [];
  const byKey = new Map<number, PrGroup>();
  for (const issue of built) {
    const key = mode === "spec" ? issue.parent ?? issue.id : issue.id;
    const existing = byKey.get(key);
    if (existing) {
      existing.members.push(issue);
    } else {
      const group = { key, members: [issue] };
      byKey.set(key, group);
      groups.push(group);
    }
  }
  return groups;
}
