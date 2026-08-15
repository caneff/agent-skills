import { test, expect, describe } from "vitest";
import {
  selectBuildable,
  selectableFrontier,
  nextBuildable,
} from "../select-buildable.mts";

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

// nextBuildable is the replan loop's per-iteration work decision, pure. It is
// selectableFrontier (buildable ∩ labeled, treating built-this-run parents as
// satisfied) minus every issue already attempted this run — so the loop makes
// progress and terminates: an issue is offered at most once, new offers appear
// only when a built parent unblocks a child, and an empty return is the fixpoint
// that ends the run.
describe("nextBuildable", () => {
  const ready = (n) => issue(n, { labels: ["ready-for-agent"] });

  test("a linear chain drains one level per iteration to a fixpoint", () => {
    // A(1) → B(2) → C(3): 2 blocked by 1, 3 blocked by 2, all ready-for-agent.
    const open = [ready(1), ready(2), ready(3)];
    const e = edges({ 2: [1], 3: [2] });

    // Iteration 1: nothing built yet — only the root A is buildable.
    let satisfied = new Set();
    let attempted = new Set();
    expect(
      nextBuildable(open, e, satisfied, attempted).map((i) => i.number)
    ).toEqual([1]);

    // A built + attempted. Iteration 2: B unblocks (parent satisfied), A excluded.
    satisfied = new Set([1]);
    attempted = new Set([1]);
    expect(
      nextBuildable(open, e, satisfied, attempted).map((i) => i.number)
    ).toEqual([2]);

    // B built + attempted. Iteration 3: C unblocks; A, B excluded.
    satisfied = new Set([1, 2]);
    attempted = new Set([1, 2]);
    expect(
      nextBuildable(open, e, satisfied, attempted).map((i) => i.number)
    ).toEqual([3]);

    // C built + attempted. Iteration 4: nothing new — fixpoint.
    satisfied = new Set([1, 2, 3]);
    attempted = new Set([1, 2, 3]);
    expect(nextBuildable(open, e, satisfied, attempted)).toEqual([]);
  });

  test("an offered-but-unbuilt issue is not re-offered (termination)", () => {
    // Root A(1) was offered and attempted but did NOT build (not in satisfied),
    // so its child B(2) never unblocks. A is excluded by attempted → fixpoint,
    // the loop cannot spin on A forever.
    const open = [ready(1), ready(2)];
    const e = edges({ 2: [1] });
    expect(
      nextBuildable(open, e, new Set(), new Set([1])).map((i) => i.number)
    ).toEqual([]);
  });

  test("independent roots are all offered in one iteration", () => {
    const open = [ready(1), ready(2), ready(3)];
    expect(
      nextBuildable(open, edges({}), new Set(), new Set())
        .map((i) => i.number)
        .sort()
    ).toEqual([1, 2, 3]);
  });

  test("the label filter still applies — an unlabeled buildable issue is dropped", () => {
    const open = [ready(1), issue(2)]; // 2 has no lifecycle label
    expect(
      nextBuildable(open, edges({}), new Set(), new Set()).map((i) => i.number)
    ).toEqual([1]);
  });
});

// Diamond guard (#342, honoring spec #340 story 11): in-run advancement stacks
// single-parent chains only. A child with 2+ parents keeps today's behavior — it
// waits until ALL its parents have actually closed (merged to main), and never
// builds while a parent has merely built this run, because resolveBase would send
// a diamond to `main` without that unmerged parent's code.
describe("nextBuildable — diamonds wait for real closure", () => {
  const ready = (n) => issue(n, { labels: ["ready-for-agent"] });

  test("a diamond child is withheld while a parent is only built-this-run", () => {
    // 3 blocked by 1 and 2; both parents still open (in-review, built this run).
    const open = [ready(1), ready(2), ready(3)];
    const e = edges({ 3: [1, 2] });
    // 1 and 2 built this run (satisfied) and attempted; 3 must NOT be offered.
    expect(
      nextBuildable(open, e, new Set([1, 2]), new Set([1, 2])).map((i) => i.number)
    ).toEqual([]);
  });

  test("a diamond child is offered once every parent has actually closed", () => {
    // 1 and 2 merged/closed → absent from the open set; 3 builds on main.
    const open = [ready(3)];
    const e = edges({ 3: [1, 2] });
    expect(
      nextBuildable(open, e, new Set(), new Set()).map((i) => i.number)
    ).toEqual([3]);
  });

  test("a diamond with one merged and one built-this-run parent still waits", () => {
    // 1 merged (closed, absent); 2 built this run (open, satisfied). 3 must wait
    // for 2 to merge — resolveBase would otherwise send it to main without 2's code.
    const open = [ready(2), ready(3)];
    const e = edges({ 3: [1, 2] });
    expect(
      nextBuildable(open, e, new Set([2]), new Set([2])).map((i) => i.number)
    ).toEqual([]);
  });
});
