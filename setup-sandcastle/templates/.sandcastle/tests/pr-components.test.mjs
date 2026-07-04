import { test, expect, describe } from "vitest";
import { prComponents } from "../pr-components.mts";

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
