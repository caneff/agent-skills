import { test, expect, describe } from "vitest";
import {
  prComponents,
  parentsFromBlockedBy,
  mergeParentEdges,
  landedIssues,
} from "../pr-components.mts";

// One PR per connected dependency component (issue #127). Components are the
// connected pieces of the parent-edge graph over the issues completed THIS run.
// Only edges to parents also completed this run count — a parent already in main
// is not part of this run's forest, so it does not join components.
//
// Fixture forest (from #126):
//   108 → 112,  120 → 119,  112/119 independent roots
//   →  main ─┬─ 112 ── 108     (component A, leaf 108)
//            └─ 119 ── 120     (component B, leaf 120)

const issue = (id, parents = [], group = undefined) => ({
  id,
  title: `issue ${id}`,
  branch: `sandcastle/issue-${id}`,
  parents,
  group,
});

// Compare components by their member id sets, order-independent.
const idSets = (comps) =>
  comps
    .map((c) => c.issues.map((i) => i.id).sort())
    .sort((a, b) => a[0].localeCompare(b[0]));
const leafIds = (comps, memberId) =>
  comps
    .find((c) => c.issues.some((i) => i.id === memberId))
    .leaves.map((l) => l.id)
    .sort();

describe("prComponents — forest fixture 108→112, 120→119", () => {
  const completed = [
    issue("112"),
    issue("119"),
    issue("108", ["112"]),
    issue("120", ["119"]),
  ];

  test("splits the two independent chains into two components", () => {
    expect(idSets(prComponents(completed))).toEqual([
      ["108", "112"],
      ["119", "120"],
    ]);
  });

  test("each component's leaf tip is the chain's child (108, 120)", () => {
    const comps = prComponents(completed);
    expect(leafIds(comps, "112")).toEqual(["108"]);
    expect(leafIds(comps, "119")).toEqual(["120"]);
  });
});

describe("prComponents — non-linear shapes", () => {
  test("a forking component (112→108, 112→109) is ONE component with two leaves", () => {
    const comps = prComponents([
      issue("112"),
      issue("108", ["112"]),
      issue("109", ["112"]),
    ]);
    expect(idSets(comps)).toEqual([["108", "109", "112"]]);
    expect(leafIds(comps, "112")).toEqual(["108", "109"]);
  });

  test("a diamond (130 ← 112,119) is ONE component with a single leaf", () => {
    const comps = prComponents([
      issue("112"),
      issue("119"),
      issue("130", ["112", "119"]),
    ]);
    expect(idSets(comps)).toEqual([["112", "119", "130"]]);
    expect(leafIds(comps, "112")).toEqual(["130"]);
  });

  test("a parent NOT completed this run (merged earlier) does not join a component", () => {
    // 130 builds on 108, but 108 is not in this run's completed set (it landed in
    // an earlier run / is in main). 130 stands alone.
    const comps = prComponents([issue("130", ["108"])]);
    expect(idSets(comps)).toEqual([["130"]]);
    expect(leafIds(comps, "130")).toEqual(["130"]);
  });

  test("a lone root is its own component and its own leaf", () => {
    const comps = prComponents([issue("112")]);
    expect(idSets(comps)).toEqual([["112"]]);
    expect(leafIds(comps, "112")).toEqual(["112"]);
  });

  test("empty input yields no components", () => {
    expect(prComponents([])).toEqual([]);
  });
});

// Topic grouping (issue #129): a PR set is a connected component of
// {parent edges} ∪ {same-group-key edges}. Topic combines independent dependency
// components into one PR; a parent edge still forces same-set (a component is the
// atomic floor and can never be split). Leaf tips stay parent-based, so a
// topic-merged set keeps one leaf per chain.
describe("prComponents — topic grouping", () => {
  test("two independent chains sharing a group become ONE PR set with both leaves", () => {
    const comps = prComponents([
      issue("112", [], "auth"),
      issue("108", ["112"], "auth"),
      issue("119", [], "auth"),
      issue("120", ["119"], "auth"),
    ]);
    expect(idSets(comps)).toEqual([["108", "112", "119", "120"]]);
    // Each chain still contributes its own leaf tip; the PR head merges both.
    expect(leafIds(comps, "112")).toEqual(["108", "120"]);
  });

  test("independent chains in DIFFERENT groups stay separate PR sets", () => {
    const comps = prComponents([
      issue("112", [], "auth"),
      issue("108", ["112"], "auth"),
      issue("119", [], "ui"),
      issue("120", ["119"], "ui"),
    ]);
    expect(idSets(comps)).toEqual([
      ["108", "112"],
      ["119", "120"],
    ]);
  });

  test("a parent edge crossing two groups still forces ONE set (component is atomic)", () => {
    // 108 builds on 112 but the planner tagged them different groups. The
    // dependency edge wins — they cannot be split across PRs.
    const comps = prComponents([
      issue("112", [], "auth"),
      issue("108", ["112"], "ui"),
    ]);
    expect(idSets(comps)).toEqual([["108", "112"]]);
  });
});

// Issue #50: the reconciliation sweep recovered stranded branches with
// parents:[], discarding the dependency graph, so a stacked recovery
// (#46 ← #47 ← #48) opened one redundant PR per tip. The fix rebuilds each
// swept branch's parents from its GitHub blockedBy edges. Every blockedBy id is
// kept as a parent; prComponents' own present-filter drops any not completed
// this run, so the sweep does no pre-restriction.
describe("parentsFromBlockedBy — sweep rebuilds the parent graph (#50)", () => {
  // Mirror the sweep's inject path: a swept CompletedIssue whose parents come
  // from its blockedBy edge list (numbers, as GitHub's graph returns them).
  const swept = (id, blockedBy = []) => ({
    id: String(id),
    title: `issue ${id}`,
    branch: `sandcastle/issue-${id}`,
    parents: parentsFromBlockedBy(blockedBy),
  });

  test("a stranded stack 46←47←48 collapses to ONE component with leaf 48", () => {
    const comps = prComponents([swept(46), swept(47, [46]), swept(48, [47])]);
    expect(comps).toHaveLength(1);
    expect(comps[0].issues.map((i) => i.id).sort()).toEqual(["46", "47", "48"]);
    expect(comps[0].leaves.map((l) => l.id)).toEqual(["48"]);
  });

  test("a blockedBy parent absent from this run is dropped, not linked", () => {
    // 48 is blocked by 47, but only 48 was recovered this run (47 already
    // merged / not in the set). The edge drops; 48 stands alone off main.
    const comps = prComponents([swept(48, [47])]);
    expect(comps).toHaveLength(1);
    expect(comps[0].issues.map((i) => i.id)).toEqual(["48"]);
    expect(comps[0].leaves.map((l) => l.id)).toEqual(["48"]);
  });
});

// Issue #90: GitHub's native sub-issue edge (a child's `parent` field) must fold
// into the same graph as the planner-declared `parents`, so a parent spec and a
// sub-issue that covers it never open as two independent PRs. mergeParentEdges is
// the pure merge: given the completed set and a childId → parentId map from
// GitHub, it appends each present parent edge to the child's `parents`, then
// prComponents groups them. The concrete regression: #77 (spec) and #78 (its
// sub-issue) both ready-for-agent, #78 carrying parent:77 but zero blockedBy —
// the planner saw two unrelated issues and Phase 3 opened #85 and #86.
describe("mergeParentEdges — fold GitHub sub-issue edges into the graph (#90)", () => {
  test("a child's parent edge groups it with its parent in ONE component", () => {
    const merged = mergeParentEdges(
      [issue("77"), issue("78")],
      new Map([["78", "77"]])
    );
    expect(idSets(prComponents(merged))).toEqual([["77", "78"]]);
  });

  test("the parent edge is appended to any planner-declared parents, deduped", () => {
    // 78 already builds on 77 per the planner; the identical GitHub edge must not
    // duplicate 77 in the parents list.
    const merged = mergeParentEdges(
      [issue("77"), issue("78", ["77"])],
      new Map([["78", "77"]])
    );
    expect(merged.find((i) => i.id === "78").parents).toEqual(["77"]);
  });

  test("a parent edge to an issue NOT completed this run drops (present-filter)", () => {
    // 78's parent 77 wasn't built this run; the edge is kept on 78 but prComponents
    // drops it, so 78 stands alone off main.
    const merged = mergeParentEdges([issue("78")], new Map([["78", "77"]]));
    expect(idSets(prComponents(merged))).toEqual([["78"]]);
  });

  test("no parent edges is an identity — issues pass through unchanged", () => {
    const input = [issue("77"), issue("78")];
    expect(mergeParentEdges(input, new Map())).toEqual(input);
  });
});

// Issue #115: a leaf whose merge conflicts is excluded from the PR head, but the
// orchestrator credited it to the PR anyway — falsifying the run summary AND
// suppressing the strand reconciliation meant to re-queue it. landedIssues asks
// what actually landed rather than tracking which merges failed: an issue is
// credited only when its branch is an ancestor of the assembled head.
describe("landedIssues — credit only what reached the PR head (#115)", () => {
  test("an issue whose branch is not an ancestor of the head is dropped", () => {
    const landed = landedIssues(
      [issue("101"), issue("102")],
      (branch) => branch !== "sandcastle/issue-102"
    );
    expect(landed.map((i) => i.id)).toEqual(["101"]);
  });

  test("a non-leaf ancestor behind a conflicting leaf tip drops too", () => {
    // Chain 105 → 106 (106 is the tip). 106 conflicts, so neither its own commits
    // nor 105's — which only reached the head through 106 — are in the head. An
    // id-set of failed LEAVES would still credit 105; ancestry does not.
    const chain = [issue("105"), issue("106", ["105"])];
    const inHead = new Set(["sandcastle/issue-101"]);
    const landed = landedIssues([...chain, issue("101")], (branch) =>
      inHead.has(branch)
    );
    expect(landed.map((i) => i.id)).toEqual(["101"]);
  });

  test("every branch an ancestor credits the whole set, order preserved", () => {
    // The no-regression case: a run where all leaf merges succeed must assign
    // exactly as before the fix.
    const set = [issue("101"), issue("104", ["101"]), issue("107")];
    expect(landedIssues(set, () => true)).toEqual(set);
  });

  test("an issue whose branch has no commits ahead of main stays credited", () => {
    // 103 completed without needing a commit, so its branch still equals main —
    // an ancestor of every head, including one whose other tip conflicted.
    // Crediting it matches pre-fix behaviour; re-queuing it would loop forever,
    // since the rebuild has nothing to add.
    const conflicted = "sandcastle/issue-102";
    const landed = landedIssues(
      [issue("101"), issue("102"), issue("103")],
      (branch) => branch !== conflicted
    );
    expect(landed.map((i) => i.id)).toEqual(["101", "103"]);
  });
});
