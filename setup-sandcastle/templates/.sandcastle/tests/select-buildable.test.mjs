import { test, expect, describe } from "vitest";
import { selectBuildable, selectableFrontier } from "../select-buildable.mts";

// selectBuildable is the deterministic frontier filter: given the open
// issues and their native GitHub `blockedBy` edges, return the buildable set —
// open issues whose every blocker has closed. A blocker counts as open only
// when it is still in the open-issue set; a closed blocker has dropped off.

const issue = (number, extra = {}) => ({
  number,
  title: `#${number}`,
  labels: [],
  ...extra,
});
const edges = (obj) => new Map(Object.entries(obj).map(([k, v]) => [+k, v]));

describe("selectBuildable", () => {
  test("an open issue with no open blockers is buildable", () => {
    const open = [issue(1), issue(2)];
    const buildable = selectBuildable(open, edges({}));
    expect(buildable.map((i) => i.number).sort()).toEqual([1, 2]);
  });

  test("an open issue with an open blocker is not buildable", () => {
    const open = [issue(1), issue(2)]; // 2 is blocked by 1, and 1 is open
    const buildable = selectBuildable(open, edges({ 2: [1] }));
    expect(buildable.map((i) => i.number)).toEqual([1]);
  });

  test("a blocker that has closed no longer blocks", () => {
    const open = [issue(2)]; // 1 has merged/closed, so it is absent from open
    const buildable = selectBuildable(open, edges({ 2: [1] }));
    expect(buildable.map((i) => i.number)).toEqual([2]);
  });

  test("a child becomes buildable only once every parent is closed", () => {
    // 3 is blocked by parents 1 and 2.
    const bothOpen = [issue(1), issue(2), issue(3)];
    expect(
      selectBuildable(bothOpen, edges({ 3: [1, 2] })).map((i) => i.number)
    ).not.toContain(3);

    const oneStillOpen = [issue(2), issue(3)]; // 1 closed, 2 still open
    expect(
      selectBuildable(oneStillOpen, edges({ 3: [1, 2] })).map((i) => i.number)
    ).not.toContain(3);

    const allClosed = [issue(3)]; // both parents closed
    expect(
      selectBuildable(allClosed, edges({ 3: [1, 2] })).map((i) => i.number)
    ).toEqual([3]);
  });

  test("preserves the full issue objects, not just their numbers", () => {
    const open = [issue(7, { title: "Fix auth", labels: ["ready-for-agent"] })];
    const [only] = selectBuildable(open, edges({}));
    expect(only).toEqual({
      number: 7,
      title: "Fix auth",
      labels: ["ready-for-agent"],
    });
  });

  // satisfiedThisRun holds ids of parents that built AND passed review this run.
  // A blocker in that set counts as satisfied even though its issue is still
  // open, so a child advances to the next chain level within one run. Absent or
  // empty, selection is exactly as before.
  test("a blocker in satisfiedThisRun no longer blocks though its issue is open", () => {
    const open = [issue(1), issue(2)]; // 1 is open but built this run
    const buildable = selectBuildable(open, edges({ 2: [1] }), new Set([1]));
    expect(buildable.map((i) => i.number).sort()).toEqual([1, 2]);
  });

  test("a child with a still-open, not-satisfied blocker stays blocked", () => {
    const open = [issue(1), issue(2)];
    const buildable = selectBuildable(open, edges({ 2: [1] }), new Set([99]));
    expect(buildable.map((i) => i.number)).toEqual([1]);
  });

  test("only every blocker satisfied makes a multi-parent child buildable", () => {
    const open = [issue(1), issue(2), issue(3)]; // 3 blocked by 1 and 2
    // just one parent satisfied — still blocked
    expect(
      selectBuildable(open, edges({ 3: [1, 2] }), new Set([1])).map((i) => i.number)
    ).not.toContain(3);
    // both parents satisfied this run — buildable
    expect(
      selectBuildable(open, edges({ 3: [1, 2] }), new Set([1, 2])).map((i) => i.number)
    ).toContain(3);
  });
});

// selectableFrontier is the whole rule the planner depends on: buildable AND
// carrying the required label. It folds the ready-for-agent post-filter that
// used to live inline in main back into the module, so both halves of the rule
// are stated and tested in one place.
describe("selectableFrontier", () => {
  const ready = (n) => issue(n, { labels: ["ready-for-agent"] });

  test("a buildable ready-for-agent issue is selectable", () => {
    const open = [ready(1), ready(2)];
    expect(
      selectableFrontier(open, edges({})).map((i) => i.number).sort()
    ).toEqual([1, 2]);
  });

  test("a buildable issue without the label is dropped", () => {
    const open = [ready(1), issue(2, { labels: ["in-review"] })];
    expect(selectableFrontier(open, edges({})).map((i) => i.number)).toEqual([
      1,
    ]);
  });

  test("an unlabeled but buildable issue is dropped", () => {
    const open = [ready(1), issue(2)]; // 2 has no lifecycle label
    expect(selectableFrontier(open, edges({})).map((i) => i.number)).toEqual([
      1,
    ]);
  });

  test("a ready-for-agent issue that is still blocked is dropped", () => {
    // 2 is ready-for-agent but blocked by open 1 — buildability wins.
    const open = [ready(1), ready(2)];
    expect(
      selectableFrontier(open, edges({ 2: [1] })).map((i) => i.number)
    ).toEqual([1]);
  });

  test("satisfiedThisRun is threaded through to buildability", () => {
    // 2 is ready and blocked only by open 1; 1 built this run → 2 selectable.
    const open = [ready(1), ready(2)];
    expect(
      selectableFrontier(open, edges({ 2: [1] }), "ready-for-agent", new Set([1]))
        .map((i) => i.number)
        .sort()
    ).toEqual([1, 2]);
  });

  test("the required label is overridable", () => {
    const open = [issue(1, { labels: ["ready-for-agent"] }), issue(2, { labels: ["queued"] })];
    expect(
      selectableFrontier(open, edges({}), "queued").map((i) => i.number)
    ).toEqual([2]);
  });
});
