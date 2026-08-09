import { test, expect, describe } from "vitest";
import {
  classifyInReviewIssue,
  bucketIssues,
  buildRunSummary,
  decideInReviewAction,
  planGateOutcome,
  planOutcomeTransition,
} from "../reconcile.mts";
import { REVIEW_RETRY_CAP } from "../retry-policy.mts";

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
  blockedByParentConflict: new Map(),
  retiredByGate: new Map(),
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

  test("multi-parent conflict block → blocked-parent-conflict, carries parents (#64)", () => {
    // #62 still holds its ready-for-agent label but was aborted this run.
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 62, title: "purge facts", labels: ["ready-for-agent"] },
        ],
        blockedByParentConflict: new Map([["62", ["60", "61"]]]),
      })
    );
    expect(result[0]).toMatchObject({
      bucket: "blocked-parent-conflict",
      blockedParents: ["60", "61"],
    });
  });

  test("block takes precedence over the ready-for-agent label (#64)", () => {
    // Same issue NOT in the block map falls through to ready-for-agent — proves
    // the block, not the label, is what redirects it.
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 62, title: "purge facts", labels: ["ready-for-agent"] },
        ],
      })
    );
    expect(result[0]).toMatchObject({ bucket: "ready-for-agent" });
  });

  // A set retired by the consecutive gate-failure cap (#25) is relabeled
  // ready-for-human and completed (in builtThisRun), yet must surface as its own
  // retired bucket — not built-this-run and not the generic ready-for-human —
  // carrying the failing tests so the summary can name them.
  test("retired-by-gate issue → retired-gate-failure, carries failing tests (#25)", () => {
    const result = bucketIssues(
      makeOpts({
        openIssues: [
          { number: 30, title: "broken", labels: ["ready-for-human"] },
        ],
        builtThisRun: new Set(["30"]),
        retiredByGate: new Map([["30", "FAIL foo.test.ts"]]),
      })
    );
    expect(result[0]).toMatchObject({
      bucket: "retired-gate-failure",
      gateFailure: "FAIL foo.test.ts",
    });
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

  test("retired-gate-failure set names the set and its failing tests (#25)", () => {
    const out = buildRunSummary([
      {
        number: 30,
        title: "broken feature",
        bucket: "retired-gate-failure",
        gateFailure: "FAIL src/foo.test.ts > does the thing",
      },
    ]);
    expect(out).toContain("#30");
    expect(out).toContain("broken feature");
    expect(out).toContain("FAIL src/foo.test.ts > does the thing");
    expect(out).toMatch(/retired|ready.for.human/i);
  });

  test("a retired-gate-failure set counts as human-gated (nothing left for the bot) (#25)", () => {
    const out = buildRunSummary([
      {
        number: 30,
        title: "broken",
        bucket: "retired-gate-failure",
        gateFailure: "FAIL foo",
      },
    ]);
    expect(out).toMatch(/all.+human.gated|nothing left for the bot/i);
  });

  test("parent-conflict block names the parents a human must merge (#64)", () => {
    const out = buildRunSummary([
      {
        number: 62,
        title: "purge facts",
        bucket: "blocked-parent-conflict",
        blockedParents: ["60", "61"],
      },
    ]);
    expect(out).toContain("parents #60, #61 conflict");
    expect(out).toMatch(/merge upstream first/);
  });

  test("a parent-conflict block counts as human-gated (nothing left for the bot) (#64)", () => {
    const out = buildRunSummary([
      {
        number: 62,
        title: "purge facts",
        bucket: "blocked-parent-conflict",
        blockedParents: ["60", "61"],
      },
    ]);
    expect(out).toMatch(/all.+human.gated|nothing left for the bot/i);
  });
});

// ---------------------------------------------------------------------------
// planGateOutcome — Phase-3 full-suite gate (#24). pass opens; any non-pass
// requeues and comments the failing tail on every issue in the set.
// ---------------------------------------------------------------------------
describe("planGateOutcome", () => {
  const set = ["101", "102", "103"];

  test("pass → open, no comments", () => {
    const plan = planGateOutcome({ status: "pass", tail: "" }, set);
    expect(plan).toEqual({ action: "open", commentIssueIds: [] });
  });

  test("test-fail → requeue, comment on every issue in the set", () => {
    const plan = planGateOutcome(
      { status: "test-fail", tail: "FAIL foo.test.ts" },
      set
    );
    expect(plan.action).toBe("requeue");
    expect(plan.commentIssueIds).toEqual(set);
  });

  test("harness-error → requeue, comment on every issue in the set", () => {
    const plan = planGateOutcome(
      { status: "harness-error", tail: "sandbox unavailable" },
      set
    );
    expect(plan.action).toBe("requeue");
    expect(plan.commentIssueIds).toEqual(set);
  });

  test("a green single-issue set opens with no comments", () => {
    expect(planGateOutcome({ status: "pass", tail: "" }, ["9"])).toEqual({
      action: "open",
      commentIssueIds: [],
    });
  });

  test("does not alias the caller's set array", () => {
    const plan = planGateOutcome({ status: "test-fail", tail: "" }, set);
    expect(plan.commentIssueIds).not.toBe(set);
  });

  // --- Consecutive gate-failure cap (#25) ---------------------------------
  // An escalated (at-cap) test-fail retires the set to a human instead of
  // requeuing it a third time. The plan preserves the work branch and carries
  // the failing tail as a summary note.
  test("escalated test-fail → retire, preserve branch, carry summary note", () => {
    const plan = planGateOutcome(
      { status: "test-fail", tail: "FAIL foo.test.ts" },
      set,
      true
    );
    expect(plan).toEqual({
      action: "retire",
      commentIssueIds: set,
      preserveBranch: true,
      summaryNote: "FAIL foo.test.ts",
    });
  });

  test("non-escalated test-fail still requeues even with escalate=false", () => {
    const plan = planGateOutcome(
      { status: "test-fail", tail: "FAIL foo.test.ts" },
      set,
      false
    );
    expect(plan.action).toBe("requeue");
  });

  // harness-error is an infra fault, never the code's — it must NOT retire even
  // if the caller (buggy) passes escalate=true. It always requeues.
  test("escalated harness-error → requeue, never retire", () => {
    const plan = planGateOutcome(
      { status: "harness-error", tail: "sandbox died" },
      set,
      true
    );
    expect(plan.action).toBe("requeue");
  });

  test("a green gate never retires regardless of escalate", () => {
    expect(planGateOutcome({ status: "pass", tail: "" }, set, true)).toEqual({
      action: "open",
      commentIssueIds: [],
    });
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

// ---------------------------------------------------------------------------
// planOutcomeTransition — the post-build label decision (#102)
// ---------------------------------------------------------------------------
describe("planOutcomeTransition", () => {
  // The below-the-cap cases below build their fixtures as REVIEW_RETRY_CAP - 1.
  // At a cap of 1 that IS the cap, and those tests would quietly start
  // asserting the escalation path instead.
  test("the cap leaves room for a below-the-cap attempt", () => {
    expect(REVIEW_RETRY_CAP).toBeGreaterThan(1);
  });

  const full = {
    mode: "full",
    id: "42",
    title: "Add widget",
    branch: "sandcastle/issue-42",
    parents: ["7"],
    group: "widgets",
  };

  test("done → in-review, dropping both buildable labels", () => {
    const plan = planOutcomeTransition({
      kind: "done",
      issue: full,
      attempts: {},
    });
    expect(plan.addLabel).toBe("in-review");
    expect([...plan.removeLabels].sort()).toEqual([
      "needs-review",
      "ready-for-agent",
    ]);
    expect(plan.escalated).toBe(false);
  });

  // The pre-extraction inline loop dropped only ready-for-agent here, leaving a
  // stale in-review label on an issue that is demonstrably NOT reviewed clean.
  // Its three sibling transitions all dropped in-review, and the downstream
  // bucketer tests in-review BEFORE needs-review — so a survivor reported the
  // issue as "human-gated: open PR pending merge" while it sat waiting to be
  // re-reviewed. Corrected here: every transition clears the labels it
  // contradicts.
  test("needs-review below the cap → needs-review, clearing the contradicted labels", () => {
    const plan = planOutcomeTransition({
      kind: "needs-review",
      issue: full,
      attempts: {},
    });
    expect(plan.addLabel).toBe("needs-review");
    expect([...plan.removeLabels].sort()).toEqual([
      "in-review",
      "ready-for-agent",
    ]);
    expect(plan.escalated).toBe(false);
    expect(plan.attempts).toEqual({ 42: 1 });
    expect(plan.attemptCount).toBe(1);
  });

  test("needs-review at the cap → escalates to a full re-implement", () => {
    const plan = planOutcomeTransition({
      kind: "needs-review",
      issue: full,
      attempts: { 42: REVIEW_RETRY_CAP - 1 },
    });
    expect(plan.addLabel).toBe("ready-for-agent");
    expect([...plan.removeLabels].sort()).toEqual([
      "in-review",
      "needs-review",
    ]);
    expect(plan.escalated).toBe(true);
    // Cleared at the cap: the next lifecycle counts from zero.
    expect(plan.attempts).toEqual({});
    expect(plan.note).toBe(
      `42 hit review-retry cap (${REVIEW_RETRY_CAP}); back to ready-for-agent for a full re-implement`
    );
  });

  test("spec-fail below the cap → back to ready-for-agent on its own counter", () => {
    const plan = planOutcomeTransition({
      kind: "spec-fail",
      issue: full,
      attempts: {},
    });
    expect(plan.addLabel).toBe("ready-for-agent");
    expect([...plan.removeLabels].sort()).toEqual([
      "in-review",
      "needs-review",
    ]);
    expect(plan.escalated).toBe(false);
    // Keyed spec-<id>, NOT <id>: the re-implement cap and the re-review cap
    // count independently for the same issue.
    expect(plan.attempts).toEqual({ "spec-42": 1 });
    // The note names the attempt out of the cap — it is the only place an
    // operator sees the count, since the plan's counters are internal.
    expect(plan.note).toBe(
      `42 failed spec review; back to ready-for-agent to re-implement (attempt 1/${REVIEW_RETRY_CAP})`
    );
  });

  test("spec-fail at the cap → handed to a human", () => {
    const plan = planOutcomeTransition({
      kind: "spec-fail",
      issue: full,
      attempts: { "spec-42": REVIEW_RETRY_CAP - 1 },
    });
    expect(plan.addLabel).toBe("ready-for-human");
    expect([...plan.removeLabels].sort()).toEqual([
      "in-review",
      "needs-review",
      "ready-for-agent",
    ]);
    expect(plan.escalated).toBe(true);
    expect(plan.attempts).toEqual({});
  });

  // The completed record is what Phase 3 groups PR sets from, so what a `done`
  // carries into it is a downstream decision, not bookkeeping.
  describe("the completed record a done outcome carries", () => {
    test("a full-mode issue keeps its forest position and topic group", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: full,
        attempts: {},
      });
      expect(plan.completed).toEqual({
        id: "42",
        title: "Add widget",
        branch: "sandcastle/issue-42",
        parents: ["7"],
        group: "widgets",
      });
    });

    // A review-only issue was picked up by label for a cheap re-review; it never
    // went through the planner, so it has no parents and no topic group. Both
    // are dropped rather than invented. `group` is absent, not "": prSets edges
    // issues together on a shared group key, so the key this record carries
    // decides PR grouping. (prSets also skips falsy keys, so "" would not fuse
    // sets today — the point is that the record states "no topic" outright
    // instead of leaning on that guard.)
    test("a review-only issue drops parents and the group key entirely", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: {
          mode: "review-only",
          id: "43",
          title: "Re-reviewed",
          branch: "sandcastle/issue-43",
        },
        attempts: {},
      });
      expect(plan.completed).toEqual({
        id: "43",
        title: "Re-reviewed",
        branch: "sandcastle/issue-43",
        parents: [],
      });
      expect("group" in plan.completed).toBe(false);
    });

    // An empty group key from the planner is "no topic", not a topic named "".
    test("a full-mode issue with an empty group key drops it too", () => {
      const plan = planOutcomeTransition({
        kind: "done",
        issue: { ...full, group: "" },
        attempts: {},
      });
      expect("group" in plan.completed).toBe(false);
    });
  });

  // No work was produced (blocked parent base, empty branch, or a pipeline that
  // threw). That says nothing about the branch, so the issue keeps the label it
  // arrived with and burns no attempt — next iteration retries it cleanly.
  test("nothing → touches no label and spends no attempt", () => {
    const plan = planOutcomeTransition({
      kind: "nothing",
      issue: full,
      attempts: { 42: 1 },
    });
    expect(plan.addLabel).toBeNull();
    expect(plan.removeLabels).toEqual([]);
    expect(plan.attempts).toEqual({ 42: 1 });
    expect(plan.attemptCount).toBe(0);
    expect(plan.escalated).toBe(false);
    expect(plan.completed).toBeUndefined();
  });

  // A re-review counter must not be spent by a spec failure, or vice versa.
  test("the two caps do not consume each other's counter", () => {
    const plan = planOutcomeTransition({
      kind: "spec-fail",
      issue: full,
      attempts: { 42: REVIEW_RETRY_CAP - 1 },
    });
    expect(plan.escalated).toBe(false);
    expect(plan.attempts).toEqual({ 42: REVIEW_RETRY_CAP - 1, "spec-42": 1 });
  });
});
