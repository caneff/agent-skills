import { test, expect, describe } from "vitest";
import {
  classifyInReviewIssue,
  bucketIssues,
  buildRunSummary,
  decideInReviewAction,
} from "../reconcile.mts";

// ---------------------------------------------------------------------------
// classifyInReviewIssue — four PR-state branches
// ---------------------------------------------------------------------------
describe("classifyInReviewIssue", () => {
  test("open PR → human-gated", () => {
    expect(classifyInReviewIssue([{ number: 5, state: "OPEN" }])).toBe(
      "human-gated"
    );
  });

  test("closed PR (no open PR) → human-vetoed", () => {
    expect(classifyInReviewIssue([{ number: 3, state: "CLOSED" }])).toBe(
      "human-vetoed"
    );
  });

  test("merged PR (no open PR) → human-vetoed", () => {
    expect(classifyInReviewIssue([{ number: 4, state: "MERGED" }])).toBe(
      "human-vetoed"
    );
  });

  test("no PRs at all → stranded", () => {
    expect(classifyInReviewIssue([])).toBe("stranded");
  });

  test("open PR wins over a closed one → human-gated", () => {
    const prs = [
      { number: 3, state: "CLOSED" },
      { number: 5, state: "OPEN" },
    ];
    expect(classifyInReviewIssue(prs)).toBe("human-gated");
  });

  test("mix of closed + merged, no open → human-vetoed", () => {
    const prs = [
      { number: 3, state: "CLOSED" },
      { number: 4, state: "MERGED" },
    ];
    expect(classifyInReviewIssue(prs)).toBe("human-vetoed");
  });
});

// ---------------------------------------------------------------------------
// bucketIssues — one bucket per type
// ---------------------------------------------------------------------------

const makeOpts = (overrides = {}) => ({
  openIssues: [],
  builtThisRun: new Set(),
  sweepInjected: new Set(),
  sweepRequeued: new Set(),
  prAssignments: new Map(),
  ...overrides,
});

describe("bucketIssues", () => {
  test("issue built this run (not sweep) → built-this-run", () => {
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

  test("issue built this run via sweep → repaired-sweep-pr", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 11, title: "repair", labels: ["in-review"] }],
        builtThisRun: new Set(["11"]),
        sweepInjected: new Set(["11"]),
        prAssignments: new Map([["11", 56]]),
      })
    );
    expect(result[0]).toMatchObject({
      bucket: "repaired-sweep-pr",
      prNumber: 56,
    });
  });

  test("issue requeued by sweep → repaired-sweep-requeued", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 12, title: "requeue", labels: ["ready-for-agent"] },
        ],
        sweepRequeued: new Set(["12"]),
      })
    );
    expect(result[0]).toMatchObject({ bucket: "repaired-sweep-requeued" });
  });

  // Regression: a sweep-injected branch whose Phase-3 merge conflicted is moved
  // to sweepRequeued (and may still be in builtThisRun + sweepInjected from the
  // injection). It must report as re-queued, never "PR opened" (the #114 loop).
  test("injected branch that conflicted (requeued, no PR) → repaired-sweep-requeued, not -pr", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 114, title: "stale", labels: ["ready-for-agent"] },
        ],
        builtThisRun: new Set(["114"]),
        sweepInjected: new Set(["114"]),
        sweepRequeued: new Set(["114"]),
        prAssignments: new Map(), // no PR landed
      })
    );
    expect(result[0].bucket).toBe("repaired-sweep-requeued");
    expect(result[0].prNumber).toBeUndefined();
  });

  // Requeued up front (stale branch), then rebuilt and PR'd in the SAME run:
  // the fresh PR is the truth — report built-this-run with its PR, not re-queued.
  test("requeued then rebuilt + PR'd this run → built-this-run with PR", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 100, title: "rebuilt", labels: ["in-review"] }],
        builtThisRun: new Set(["100"]),
        sweepRequeued: new Set(["100"]),
        prAssignments: new Map([["100", 200]]),
      })
    );
    expect(result[0].bucket).toBe("built-this-run");
    expect(result[0].prNumber).toBe(200);
  });

  // Honesty gate: injected, not requeued, but no PR assigned → don't claim a
  // sweep repair PR; fall back to built-this-run rather than lying.
  test("injected without a PR number → not repaired-sweep-pr", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 13, title: "noPR", labels: ["in-review"] }],
        builtThisRun: new Set(["13"]),
        sweepInjected: new Set(["13"]),
        prAssignments: new Map(),
      })
    );
    expect(result[0].bucket).not.toBe("repaired-sweep-pr");
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

  test("needs-review issue → in-flight-needs-review", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 15, title: "nr", labels: ["needs-review"] }],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "in-flight-needs-review" });
  });

  test("no lifecycle label → human-gated-untriaged", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [{ number: 16, title: "prd", labels: [] }],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "human-gated-untriaged" });
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

// ---------------------------------------------------------------------------
// buildRunSummary — format checks
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// decideInReviewAction — truth table
// ---------------------------------------------------------------------------
describe("decideInReviewAction", () => {
  test("human-gated → leave", () => {
    expect(
      decideInReviewAction("human-gated", {
        branchExists: false,
        mergesClean: false,
      })
    ).toBe("leave");
  });

  test("human-vetoed → relabel-human", () => {
    expect(
      decideInReviewAction("human-vetoed", {
        branchExists: true,
        mergesClean: true,
      })
    ).toBe("relabel-human");
  });

  test("stranded, no branch → requeue", () => {
    expect(
      decideInReviewAction("stranded", {
        branchExists: false,
        mergesClean: false,
      })
    ).toBe("requeue");
  });

  test("stranded, branch exists but conflicts with main → requeue", () => {
    expect(
      decideInReviewAction("stranded", {
        branchExists: true,
        mergesClean: false,
      })
    ).toBe("requeue");
  });

  test("stranded, branch exists and merges clean → inject", () => {
    expect(
      decideInReviewAction("stranded", {
        branchExists: true,
        mergesClean: true,
      })
    ).toBe("inject");
  });

  test("stranded, branch absent but mergesClean true (shouldn't inject without branch) → requeue", () => {
    expect(
      decideInReviewAction("stranded", {
        branchExists: false,
        mergesClean: true,
      })
    ).toBe("requeue");
  });
});
