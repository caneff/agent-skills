import { test, expect, describe } from "vitest";
import { selectBuildable } from "../select-buildable.mts";

// selectBuildable is the deterministic frontier filter (#242): given the open
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
});
