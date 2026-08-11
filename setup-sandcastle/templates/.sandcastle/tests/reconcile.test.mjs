import { test, expect, describe } from "vitest";
import {
  bucketIssues,
  buildRunSummary,
  deliveredParentIds,
  planOutcomeTransition,
} from "../reconcile.mts";

const makeOpts = (overrides = {}) => ({
  openIssues: [],
  builtThisRun: new Set(),
  prAssignments: new Map(),
  deliveredParents: new Set(),
  ...overrides,
});

describe("bucketIssues", () => {
  test("issue built this run → built-this-run with its PR", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 10, title: "feat", labels: ["in-review"] }],
        builtThisRun: new Set(["10"]),
        prAssignments: new Map([["10", 55]]),
      })
    );
    expect(result[0]).toMatchObject({
      bucket: "built-this-run",
      number: 10,
      prNumber: 55,
    });
  });

  test("in-review issue not built this run → human-gated-pr", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 13, title: "old", labels: ["in-review"] }],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "human-gated-pr" });
  });

  test("ready-for-human issue → human-gated-ready-for-human", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 14, title: "rfh", labels: ["ready-for-human"] }],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "human-gated-ready-for-human" });
  });

  test("no lifecycle label → human-gated-untriaged", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 16, title: "prd", labels: [] }],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "human-gated-untriaged" });
  });

  // A spent parent (children all closed) surfaces as ready-to-close, and does so
  // even when it still carries a stray lifecycle label — the close reminder must
  // win over that label. This is the case that lingered open as ready-for-human.
  test("delivered parent with a stray label → human-gated-delivered-parent", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 99, title: "spec: nine fixes", labels: ["ready-for-human"] },
        ],
        deliveredParents: new Set(["99"]),
      })
    );
    expect(result[0]).toMatchObject({
      bucket: "human-gated-delivered-parent",
    });
  });

  test("ready-for-agent not built this run → ready-for-agent", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 17, title: "blocked", labels: ["ready-for-agent"] },
        ],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "ready-for-agent" });
  });

  test("empty issue list → empty result", () => {
    expect(bucketIssues(makeOpts())).toEqual([]);
  });
});

describe("deliveredParentIds", () => {
  test("open parent, every child closed → flagged", () => {
    const edges = [
      { number: 99, state: "OPEN", parent: null },
      { number: 100, state: "CLOSED", parent: 99 },
      { number: 101, state: "CLOSED", parent: 99 },
    ];
    expect(deliveredParentIds(edges)).toEqual(new Set(["99"]));
  });

  test("one child still open → not flagged", () => {
    const edges = [
      { number: 99, state: "OPEN", parent: null },
      { number: 100, state: "CLOSED", parent: 99 },
      { number: 101, state: "OPEN", parent: 99 },
    ];
    expect(deliveredParentIds(edges)).toEqual(new Set());
  });

  test("parent already closed → not flagged (nothing to close)", () => {
    const edges = [
      { number: 99, state: "CLOSED", parent: null },
      { number: 100, state: "CLOSED", parent: 99 },
    ];
    expect(deliveredParentIds(edges)).toEqual(new Set());
  });

  test("childless open issue → not a parent, not flagged", () => {
    const edges = [{ number: 42, state: "OPEN", parent: null }];
    expect(deliveredParentIds(edges)).toEqual(new Set());
  });
});

describe("buildRunSummary", () => {
  test("includes section header", () => {
    expect(buildRunSummary([])).toContain("Run Summary");
  });

  test("lists built issues with PR number", () => {
    const bucketed = [
      { number: 10, title: "feat", bucket: "built-this-run", prNumber: 55 },
    ];
    const out = buildRunSummary(bucketed);
    expect(out).toContain("#10");
    expect(out).toContain("PR #55");
  });

  test("lists untriaged issues", () => {
    const bucketed = [
      {
        number: 99,
        title: "PRD: new feature",
        bucket: "human-gated-untriaged",
      },
    ];
    const out = buildRunSummary(bucketed);
    expect(out).toContain("#99");
    expect(out).toContain("untriaged");
  });

  test("flags uncategorized issues loudly as BUG", () => {
    const bucketed = [
      { number: 77, title: "mystery", bucket: "uncategorized" },
    ];
    const out = buildRunSummary(bucketed);
    expect(out).toContain("BUG");
    expect(out).toContain("#77");
  });

  test("all-human-gated run reports that nothing is left for the bot", () => {
    const bucketed = [
      { number: 5, title: "a", bucket: "human-gated-pr" },
      { number: 6, title: "b", bucket: "human-gated-untriaged" },
    ];
    const out = buildRunSummary(bucketed);
    expect(out).toMatch(/all.+human.gated|nothing left for the bot/i);
  });
});

describe("planOutcomeTransition", () => {
  const full = {
    id: "42",
    title: "Add widget",
    branch: "sandcastle/issue-42",
    parents: ["7"],
    group: "widgets",
  };

  test("done → in-review, dropping the buildable label; branch not preserved", () => {
    const plan = planOutcomeTransition({ kind: "done", issue: full });
    expect(plan.addLabel).toBe("in-review");
    expect(plan.removeLabels).toEqual(["ready-for-agent"]);
    expect(plan.preserveBranch).toBe(false);
    expect(plan.failureSection).toBeUndefined();
  });

  test("review-fail → ready-for-human, branch preserved, no PR path", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
    });
    expect(plan.addLabel).toBe("ready-for-human");
    expect(plan.removeLabels).toEqual(["ready-for-agent"]);
    expect(plan.preserveBranch).toBe(true);
    expect(plan.completed).toBeUndefined();
    expect(plan.note).toBe(
      "42 failed review (spec); no PR — branch preserved, handed to a human (ready-for-human)"
    );
  });

  test("a standards-only failure names standards, not spec", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["standards"],
    });
    expect(plan.note).toContain("failed review (standards)");
    expect(plan.failureSection).toContain("**standards**");
  });

  test("both axes failing names both, in the note and the section", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec", "standards"],
    });
    expect(plan.note).toContain("failed review (spec, standards)");
    expect(plan.failureSection).toContain("**spec**");
    expect(plan.failureSection).toContain("**standards**");
  });

  test("no axes given → reads as 'review' rather than an empty bracket", () => {
    const plan = planOutcomeTransition({ kind: "review-fail", issue: full });
    expect(plan.note).toContain("failed review (review)");
    expect(plan.failureSection).toContain("**review**");
  });

  // The failure section is the human's whole brief: it must name the preserved
  // branch and the exact `git worktree add` that continues it (not EnterWorktree),
  // and point at /implement.
  test("the failure section carries the continue-the-branch instruction", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
    });
    expect(plan.failureSection).toContain("/implement 42");
    expect(plan.failureSection).toContain(
      "git worktree add ../issue-42 sandcastle/issue-42"
    );
    expect(plan.failureSection).toContain("sandcastle/issue-42");
  });

  // The reviewer's per-axis reason is embedded so the human sees why without
  // opening the run log.
  test("a per-axis reason is embedded in the failure section", () => {
    const plan = planOutcomeTransition({
      kind: "review-fail",
      issue: full,
      failedAxes: ["spec"],
      reasons: { spec: "missing the idempotency requirement" },
    });
    expect(plan.failureSection).toContain(
      "missing the idempotency requirement"
    );
  });

  test("nothing → touches no label, preserves no branch, records nothing", () => {
    const plan = planOutcomeTransition({ kind: "nothing", issue: full });
    expect(plan.addLabel).toBeNull();
    expect(plan.removeLabels).toEqual([]);
    expect(plan.preserveBranch).toBe(false);
    expect(plan.completed).toBeUndefined();
  });

  // The completed record is what the run summary counts a build from.
  describe("the completed record a done outcome carries", () => {
    test("a full-mode issue keeps its forest position and topic group", () => {
      const plan = planOutcomeTransition({ kind: "done", issue: full });
      expect(plan.completed).toEqual({
        id: "42",
        title: "Add widget",
        branch: "sandcastle/issue-42",
        parents: ["7"],
        group: "widgets",
      });
    });

    test("an issue with no parents and an empty group carries neither", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: {
          id: "43",
          title: "Re-reviewed",
          branch: "sandcastle/issue-43",
          parents: [],
          group: "",
        },
      });
      expect(plan.completed).toEqual({
        id: "43",
        title: "Re-reviewed",
        branch: "sandcastle/issue-43",
        parents: [],
      });
      expect("group" in plan.completed).toBe(false);
    });

    test("an issue with an empty group key drops it too", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: { ...full, group: "" },
      });
      expect("group" in plan.completed).toBe(false);
    });
  });
});
