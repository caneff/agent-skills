// PR-set detection for per-set PRs (issues #127 + #129).
//
// A run builds a dependency FOREST: each issue's branch is cut from its parent's
// branch (or main). At PR time we open ONE pull request per PR SET — a connected
// component of `{parent edges} ∪ {same-group edges}`. Dependency links and a
// shared topic `group` both pull issues into one set; a dependency edge always
// wins, so a chain is never split (a component is the atomic floor — #127), while
// topic only combines otherwise-independent components (#129). Each set is
// independent off main (no shared commits), so its PRs merge in any order with no
// rebase surgery.
//
// Only edges to parents ALSO completed this run count. A parent already in main
// (it landed in an earlier run) is not part of this run's forest, so it does not
// pull its dependent into a set — the dependent stands alone off main.
//
// Pure function: no git, unit-testable. The orchestrator passes the issues it
// recorded as `done` this run.

export interface CompletedIssue {
  id: string;
  title: string;
  branch: string;
  parents: string[];
  // Topic key from the planner (issue #129). Issues sharing a non-empty group are
  // combined into one PR even when no dependency links them. Undefined/empty means
  // "no topic" — the issue groups only by its dependency edges.
  group?: string;
}

export interface PrComponent {
  // Every issue in this connected component.
  issues: CompletedIssue[];
  // Leaf tips: members no other member of this component builds on. A child
  // branch transitively contains its ancestors, so merging just the leaves pulls
  // in the whole component exactly once. A linear chain has one leaf; a fork has
  // several; a diamond collapses back to one.
  leaves: CompletedIssue[];
}

// Rebuild a swept branch's `parents` from its GitHub `blockedBy` edges (issue
// #50). The reconciliation sweep recovers a stranded branch but used to inject
// `parents: []`, discarding the dependency graph — a stacked recovery then
// opened one redundant PR per tip. `blockedBy` is the durable ground truth on
// the issues, so the sweep reconstructs parents from it. Every edge is kept as a
// string id (matching `parents`); `prComponents` drops any not completed this
// run via its own present-filter, so there is no pre-restriction here. Purely
// inferred parents (file-overlap edges with no `blockedBy` behind them) can't be
// recovered post-crash and are the known gap.
export function parentsFromBlockedBy(blockedBy: number[]): string[] {
  return blockedBy.map(String);
}

// Fold GitHub's native sub-issue edge into each issue's `parents` (issue #90).
// A child linked to a parent via GitHub's `parent` field — not `blockedBy`, and
// regardless of what the LLM planner declared — carries that intent invisibly:
// the planner (soft guidance) can still miss it, so a parent spec and a child
// that supersedes it get built independently and open as two PRs. `parentOf`
// maps childId → parentId from GitHub; this appends each edge to the child's
// `parents` (deduped), and `prComponents`' own present-filter drops any parent
// not completed this run — so an edge to an already-merged parent is a no-op.
export function mergeParentEdges(
  issues: CompletedIssue[],
  parentOf: Map<string, string>
): CompletedIssue[] {
  return issues.map((issue) => {
    const p = parentOf.get(issue.id);
    if (!p || issue.parents.includes(p)) return issue;
    return { ...issue, parents: [...issue.parents, p] };
  });
}

// Which of a PR set's issues actually reached the assembled head (issue #115).
//
// The head is built by merging the set's leaf tips; a tip whose merge conflicts is
// aborted and excluded, and its commits never land. Crediting the whole set
// regardless both falsified the run summary and suppressed the strand
// reconciliation, which skips any issue already carrying a PR assignment.
//
// Outcome-based, not failure-tracked: `isAncestor` answers "did this branch reach
// the head", so a conflicting tip drops AND so does its whole ancestor chain,
// whose commits only ever reached the head through that tip. A set of failed leaf
// ids would miss those ancestors. Pure — the caller supplies the predicate.
export function landedIssues(
  issues: CompletedIssue[],
  isAncestor: (branch: string) => boolean
): CompletedIssue[] {
  return issues.filter((i) => isAncestor(i.branch));
}

// Partition completed issues into connected components by parent edges, each with
// its leaf tips. Component order follows first appearance in `issues`.
export function prComponents(issues: CompletedIssue[]): PrComponent[] {
  const present = new Set(issues.map((i) => i.id));

  // Union-find over issue ids. Only edges between two completed issues union.
  const parent = new Map<string, string>(issues.map((i) => [i.id, i.id]));
  const find = (x: string): string => {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    // Path compression.
    let cur = x;
    while (parent.get(cur) !== root) {
      const next = parent.get(cur)!;
      parent.set(cur, root);
      cur = next;
    }
    return root;
  };
  const union = (a: string, b: string): void => {
    parent.set(find(a), find(b));
  };
  for (const issue of issues) {
    for (const p of issue.parents) {
      if (present.has(p)) union(issue.id, p);
    }
  }

  // Topic edges (issue #129): union all issues sharing a non-empty group key, so
  // independent dependency components on the same topic land in one PR set. Parent
  // edges already unioned above, so a dependency that crosses groups still wins —
  // a component is never split, only combined.
  const groupRep = new Map<string, string>();
  for (const issue of issues) {
    if (!issue.group) continue;
    const rep = groupRep.get(issue.group);
    if (rep === undefined) groupRep.set(issue.group, issue.id);
    else union(issue.id, rep);
  }

  // Leaf tips stay PARENT-based: a topic-merged set keeps one leaf per chain, and
  // the PR head merges them all. An issue referenced as a parent by a fellow
  // completed issue is not a leaf.
  const referencedParents = new Set(
    issues.flatMap((i) => i.parents).filter((p) => present.has(p))
  );

  // Group by component root, preserving first-appearance order.
  const components = new Map<string, PrComponent>();
  for (const issue of issues) {
    const root = find(issue.id);
    if (!components.has(root)) components.set(root, { issues: [], leaves: [] });
    const comp = components.get(root)!;
    comp.issues.push(issue);
    if (!referencedParents.has(issue.id)) comp.leaves.push(issue);
  }
  return [...components.values()];
}
