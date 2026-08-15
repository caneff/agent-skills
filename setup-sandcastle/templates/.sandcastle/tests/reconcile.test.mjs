import { test, expect, describe } from "vitest";
import {
  bucketIssues,
  buildRunSummary,
  deliveredParentIds,
  orderMergesBaseFirst,
  deriveDammed,
} from "../reconcile.mts";
// planOutcomeTransition moved to issue-lifecycle.mts (#274) — its tests moved
// with it, to tests/issue-lifecycle.test.mjs.

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

  // #344 — the run-scoped roll-up: Stuck, Dammed, Next. The 4 tests above
  // called buildRunSummary with one arg; they must stay green with the new
  // blocks simply omitted (default run = {}).

  test("review-fail renders under Stuck with its failing axis", () => {
    const out = buildRunSummary([], {
      stuck: [
        {
          kind: "review-fail",
          number: 103,
          title: "Validate config schema",
          failedAxes: ["standards"],
          why: "2 functions over the 40-line limit; error path untested.",
          branch: "sandcastle/issue-103",
        },
      ],
    });
    expect(out).toContain("Stuck");
    expect(out).toContain("[review-fail]");
    expect(out).toContain("#103");
    expect(out).toContain(
      "standards: 2 functions over the 40-line limit; error path untested."
    );
    expect(out).toContain("sandcastle/issue-103");
  });

  test("error renders under Stuck with labels-untouched wording", () => {
    const out = buildRunSummary([], {
      stuck: [
        { kind: "error", number: 111, title: "Migrate to new logger API" },
      ],
    });
    expect(out).toContain("[error]");
    expect(out).toContain("#111");
    expect(out).toMatch(/labels untouched/i);
  });

  test("tags are plain text, never emoji", () => {
    const out = buildRunSummary([], {
      stuck: [
        {
          kind: "review-fail",
          number: 1,
          title: "a",
          failedAxes: ["spec"],
          branch: "b",
        },
        { kind: "error", number: 2, title: "b" },
      ],
    });
    // no emoji characters anywhere in the rendered Stuck block. "→" (used for
    // the PR/re-drive pointer, per the pinned prototype) is plain text, not
    // emoji, so the arrows block is deliberately excluded from this check.
    expect(out).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
    expect(out).toContain("[review-fail]");
    expect(out).toContain("[error]");
  });

  test("child of a failed parent renders under Dammed with its waitsOn", () => {
    const out = buildRunSummary([], {
      dammed: [
        { number: 104, title: "Persist validated config", waitsOn: 103 },
      ],
    });
    expect(out).toContain("Dammed");
    expect(out).toContain("#104");
    expect(out).toContain("waits on #103");
  });

  test("healthy queued child with no dammed entries omits the Dammed block", () => {
    const out = buildRunSummary([], {});
    expect(out).not.toContain("Dammed");
  });

  test("Next footer emits merge lines in given order plus the re-run line", () => {
    const out = buildRunSummary([], {
      nextMerges: [
        { pr: 340, issue: 101, note: "base of the stack" },
        { pr: 341, issue: 102, note: "stacked on #101" },
        { pr: 342, issue: 110, note: "independent" },
      ],
    });
    const iA = out.indexOf("gh pr merge 340");
    const iB = out.indexOf("gh pr merge 341");
    const iC = out.indexOf("gh pr merge 342");
    const iWatch = out.indexOf("/sandcastle-watch");
    expect(iA).toBeGreaterThan(-1);
    expect(iB).toBeGreaterThan(iA);
    expect(iC).toBeGreaterThan(iB);
    expect(iWatch).toBeGreaterThan(iC);
    expect(out).toContain("# #101, base of the stack");
    expect(out).toContain("# #102, stacked on #101");
    expect(out).toContain("--squash --delete-branch");
  });

  test("empty run object omits Stuck/Dammed/Next blocks entirely", () => {
    const bucketed = [
      { number: 10, title: "feat", bucket: "built-this-run", prNumber: 55 },
    ];
    const out = buildRunSummary(bucketed);
    expect(out).not.toContain("Stuck");
    expect(out).not.toContain("Dammed");
    expect(out).not.toContain("Next");
  });

  // A review-fail issue still carries its (relabeled) ready-for-human bucket,
  // and a dammed issue still carries ready-for-agent — bucketIssues has no way
  // to know either happened. Without a dedup pass here, both would render
  // twice: once under Stuck/Dammed, once under the old human-gated/available
  // sections. The prototype shows each issue exactly once (#344).
  test("a stuck issue is not duplicated under its old human-gated bucket", () => {
    const bucketed = [
      {
        number: 103,
        title: "Validate config schema",
        bucket: "human-gated-ready-for-human",
      },
    ];
    const out = buildRunSummary(bucketed, {
      stuck: [
        {
          kind: "review-fail",
          number: 103,
          title: "Validate config schema",
          failedAxes: ["standards"],
          branch: "sandcastle/issue-103",
        },
      ],
    });
    expect(out).toContain("[review-fail]");
    expect(out).not.toContain("Human-gated: ready for human");
  });

  test("a dammed issue is not duplicated under Available", () => {
    const bucketed = [
      { number: 104, title: "Persist validated config", bucket: "ready-for-agent" },
    ];
    const out = buildRunSummary(bucketed, {
      dammed: [
        { number: 104, title: "Persist validated config", waitsOn: 103 },
      ],
    });
    expect(out).toContain("Dammed behind a failure");
    expect(out).not.toContain("Available (queued / blocked)");
  });
});

describe("orderMergesBaseFirst", () => {
  test("chain: parent before child", () => {
    const result = orderMergesBaseFirst([
      { issue: 102, pr: 341, baseParent: 101 },
      { issue: 101, pr: 340, baseParent: null },
    ]);
    expect(result.map((r) => r.issue)).toEqual([101, 102]);
  });

  test("independent entries keep stable input order", () => {
    const result = orderMergesBaseFirst([
      { issue: 110, pr: 342, baseParent: null },
      { issue: 101, pr: 340, baseParent: null },
      { issue: 102, pr: 341, baseParent: 101 },
    ]);
    expect(result.map((r) => r.issue)).toEqual([110, 101, 102]);
  });
});

describe("deriveDammed", () => {
  const openIssues = [
    { number: 103, title: "Validate config schema", labels: [] },
    { number: 104, title: "Persist validated config", labels: [] },
    { number: 105, title: "Config hot-reload", labels: [] },
    { number: 106, title: "Healthy queued child", labels: [] },
  ];

  test("direct child of a failed parent → dammed, waitsOn = parent", () => {
    const blockedBy = new Map([
      [104, [103]],
      [106, [999]], // parent not failed
    ]);
    const result = deriveDammed(
      openIssues,
      blockedBy,
      new Set([103]),
      new Set()
    );
    expect(result).toContainEqual({
      number: 104,
      title: "Persist validated config",
      waitsOn: 103,
    });
  });

  test("grandchild of a failed root → dammed, waitsOn = its dammed parent", () => {
    const blockedBy = new Map([
      [104, [103]],
      [105, [104]],
    ]);
    const result = deriveDammed(
      openIssues,
      blockedBy,
      new Set([103]),
      new Set()
    );
    const grandchild = result.find((r) => r.number === 105);
    expect(grandchild).toEqual({
      number: 105,
      title: "Config hot-reload",
      waitsOn: 104,
    });
  });

  test("healthy queued child whose parent did not fail is not dammed", () => {
    const blockedBy = new Map([[106, [999]]]);
    const result = deriveDammed(
      openIssues,
      blockedBy,
      new Set([103]),
      new Set()
    );
    expect(result.find((r) => r.number === 106)).toBeUndefined();
  });

  test("an issue built this run is never dammed even if its blocker failed", () => {
    const blockedBy = new Map([[104, [103]]]);
    const result = deriveDammed(
      openIssues,
      blockedBy,
      new Set([103]),
      new Set([104])
    );
    expect(result.find((r) => r.number === 104)).toBeUndefined();
  });
});
