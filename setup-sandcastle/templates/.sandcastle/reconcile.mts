// Pure functions for reconciliation sweep and bucketed run summary.
//
// classifyInReviewIssue: classify a single in-review issue based on its PRs.
// bucketIssues: bucket all open issues for the end-of-run summary.
// buildRunSummary: format the bucketed summary as a printable string.
// planGateOutcome: decide open-vs-requeue from the Phase-3 full-suite verdict.
// planOutcomeTransition: decide one issue's labels from its post-build outcome.

import type { CheckVerdict, ReviewAxis } from "./review-verdict.mts";
import type { CompletedIssue } from "./pr-components.mts";
import { recordAttempt, REVIEW_RETRY_CAP, type Attempts } from "./retry-policy.mts";

// ---------------------------------------------------------------------------
// Reconciliation sweep — classifyInReviewIssue
// ---------------------------------------------------------------------------

export type PrState = "OPEN" | "CLOSED" | "MERGED";

export interface PrRef {
  number: number;
  state: PrState;
}

// How an in-review issue should be handled by the reconciliation sweep.
//   human-gated  — an open PR references it; leave untouched.
//   human-vetoed — only closed-unmerged PR(s) reference it; relabel ready-for-human.
//   stranded     — no PR references it at all; route based on branch state.
export type InReviewClassification =
  | "human-gated"
  | "human-vetoed"
  | "stranded";

// Action the sweep should take for a single in-review issue.
//   leave         — human-gated (open PR exists); do nothing
//   relabel-human — human-vetoed; relabel ready-for-human
//   inject        — stranded, branch exists and merges clean; inject for Phase 3 PR
//   requeue       — stranded, no usable branch; relabel ready-for-agent, delete stale branch
export type InReviewAction = "leave" | "relabel-human" | "inject" | "requeue";

export function decideInReviewAction(
  classification: InReviewClassification,
  opts: { branchExists: boolean; mergesClean: boolean }
): InReviewAction {
  if (classification === "human-gated") return "leave";
  if (classification === "human-vetoed") return "relabel-human";
  // stranded
  return opts.branchExists && opts.mergesClean ? "inject" : "requeue";
}

export function classifyInReviewIssue(prs: PrRef[]): InReviewClassification {
  if (prs.some((pr) => pr.state === "OPEN")) return "human-gated";
  if (prs.some((pr) => pr.state === "CLOSED" || pr.state === "MERGED"))
    return "human-vetoed";
  return "stranded";
}

// ---------------------------------------------------------------------------
// Phase-3 full-suite gate — planGateOutcome (#22 / #24)
// ---------------------------------------------------------------------------

export type GateAction = "open" | "requeue" | "retire";

export interface GatePlan {
  //   open    — the suite is green; push the head and open the PR as today.
  //   requeue — non-green; do NOT open the PR. main.mts posts the failing tail
  //             on commentIssueIds and leaves the set PR-less, so the existing
  //             post-Phase-3 reconciliation relabels it ready-for-agent and
  //             deletes the stale branch for a fresh rebuild next iteration.
  //   retire  — a real test-fail that has now failed the gate REVIEW_RETRY_CAP
  //             times running (#25). Do NOT requeue again — a deterministically
  //             broken set would loop forever. main.mts relabels the set
  //             ready-for-human, PRESERVES the work branch (see preserveBranch),
  //             and names it + its failing tests in the run summary.
  action: GateAction;
  // Issues to comment the bounded failing tail on: every issue in the set on a
  // non-pass, empty on pass. The tail itself rides on the verdict (verdict.tail);
  // this only carries WHICH issues get it.
  commentIssueIds: string[];
  // retire only: keep the set's work branch instead of deleting it in the
  // post-Phase-3 reconciliation, so the human inherits the actual failing tree.
  preserveBranch?: boolean;
  // retire only: the bounded failing tail, forwarded to the run summary so the
  // retired set's failing tests are named there, not just on the issues.
  summaryNote?: string;
}

// Gate a PR set on its merged head's full-suite CHECK verdict. A green suite
// ("pass") opens the PR. A non-pass never opens it: normally the set is requeued
// (every issue commented with the failing tail, then rebuilt next iteration),
// but once a REAL "test-fail" has escalated — hit the consecutive-failure cap
// the caller tracks per issue under key gate-<id> (#25) — the set is RETIRED to a
// human instead of looping forever. "harness-error" is an infra fault, never the
// code's: it always requeues and is never counted toward the cap, so it can
// never escalate here even if the caller passes escalated by mistake. Pure:
// main.mts executes the returned plan.
export function planGateOutcome(
  verdict: CheckVerdict,
  setIssueIds: string[],
  escalated = false
): GatePlan {
  if (verdict.status === "pass") return { action: "open", commentIssueIds: [] };
  if (escalated && verdict.status === "test-fail")
    return {
      action: "retire",
      commentIssueIds: [...setIssueIds],
      preserveBranch: true,
      summaryNote: verdict.tail,
    };
  return { action: "requeue", commentIssueIds: [...setIssueIds] };
}

// ---------------------------------------------------------------------------
// Post-build outcome — planOutcomeTransition (#102)
// ---------------------------------------------------------------------------

// What the execute+review pipeline concluded for one issue.
//   done         — implemented and reviewed clean; belongs in a PR set.
//   needs-review — the reviewer errored; the branch is fine, re-review it.
//   review-fail  — reviewed, but a review axis (spec and/or standards) failed;
//                  `failedAxes` names which. Re-implemented up to the cap.
//   nothing      — no work happened: a multi-parent base conflict blocked the
//                  issue, or the branch has no diff vs main. main.mts also maps
//                  a rejected pipeline (sandbox crash, network) here.
export type OutcomeKind = "done" | "needs-review" | "review-fail" | "nothing";

// The issue as the execute loop knows it. A full-mode issue came from the
// planner and carries its forest position (parents) and topic group; a
// review-only issue was picked up by label for a cheap re-review and has
// neither.
export type OutcomeIssue =
  | {
      mode: "full";
      id: string;
      title: string;
      branch: string;
      parents: string[];
      group?: string;
    }
  | { mode: "review-only"; id: string; title: string; branch: string };

export interface OutcomePlan {
  // Label to add, or null when the outcome touches no label at all.
  addLabel: string | null;
  removeLabels: string[];
  // Counters to persist after this outcome — already incremented, cleared, or
  // untouched. Never the caller's object: every path returns a fresh one.
  attempts: Attempts;
  // How many failed attempts this outcome makes, 0 when it records none. NOT
  // readable back out of `attempts`: at the cap recordAttempt clears the
  // counter, so an escalating outcome reports count 2 with the key gone.
  attemptCount: number;
  // This outcome hit REVIEW_RETRY_CAP and changed lifecycle because of it.
  escalated: boolean;
  // done only: the PR-set membership record main.mts accumulates.
  completed?: CompletedIssue;
  // Operator-facing line main.mts prints, unindented — the caller owns layout.
  // Absent when there is nothing to say.
  note?: string;
}

export function planOutcomeTransition(input: {
  kind: OutcomeKind;
  issue: OutcomeIssue;
  attempts: Attempts;
  // The review axes that failed, for a review-fail outcome — names the axis in
  // the operator note instead of always saying "spec". Absent otherwise.
  failedAxes?: ReviewAxis[];
}): OutcomePlan {
  const { kind, issue, attempts, failedAxes } = input;

  if (kind === "done") {
    // Reviewed clean, so the retry counter is reset rather than incremented —
    // a later failure starts its count from zero.
    const next = { ...attempts };
    delete next[issue.id];
    return {
      addLabel: "in-review",
      removeLabels: ["ready-for-agent", "needs-review"],
      attempts: next,
      attemptCount: 0,
      escalated: false,
      completed: {
        id: issue.id,
        title: issue.title,
        branch: issue.branch,
        parents: issue.mode === "full" ? issue.parents : [],
        ...(issue.mode === "full" && issue.group
          ? { group: issue.group }
          : {}),
      },
    };
  }

  if (kind === "needs-review") {
    const r = recordAttempt(attempts, issue.id);
    // At the cap, cheap re-review has provably failed to salvage the branch.
    // Only a full implement pass can change the code, so hand it back to the
    // implementer rather than queueing a re-review that will fail the same way.
    if (r.escalate)
      return {
        addLabel: "ready-for-agent",
        removeLabels: ["needs-review", "in-review"],
        attempts: r.attempts,
        attemptCount: r.count,
        escalated: true,
        note: `${issue.id} hit review-retry cap (${REVIEW_RETRY_CAP}); back to ready-for-agent for a full re-implement`,
      };
    return {
      addLabel: "needs-review",
      removeLabels: ["ready-for-agent", "in-review"],
      attempts: r.attempts,
      attemptCount: r.count,
      escalated: false,
    };
  }

  if (kind === "review-fail") {
    // Re-review cannot repair a failing review axis — only re-implementing can.
    // Both axes share one cap, counted under review-<id> so a persistently-
    // failing issue burns its own cap rather than the re-review one.
    const axes = failedAxes?.length ? failedAxes.join(", ") : "review";
    const r = recordAttempt(attempts, `review-${issue.id}`);
    if (r.escalate)
      return {
        addLabel: "ready-for-human",
        removeLabels: ["ready-for-agent", "needs-review", "in-review"],
        attempts: r.attempts,
        attemptCount: r.count,
        escalated: true,
        note: `${issue.id} failed review (${axes}) ${REVIEW_RETRY_CAP}x; handing to a human (ready-for-human)`,
      };
    return {
      addLabel: "ready-for-agent",
      removeLabels: ["needs-review", "in-review"],
      attempts: r.attempts,
      attemptCount: r.count,
      escalated: false,
      note: `${issue.id} failed review (${axes}); back to ready-for-agent to re-implement (attempt ${r.count}/${REVIEW_RETRY_CAP})`,
    };
  }

  // "nothing": no work was produced, which is a verdict on the run, not on the
  // branch. Leave the issue exactly as it arrived — it keeps ready-for-agent
  // and is retried cleanly. Counting an attempt here would spend a retry cap on
  // an issue that was never actually reviewed.
  return {
    addLabel: null,
    removeLabels: [],
    attempts: { ...attempts },
    attemptCount: 0,
    escalated: false,
  };
}

// ---------------------------------------------------------------------------
// Bucketed run summary — bucketIssues + buildRunSummary
// ---------------------------------------------------------------------------

export interface OpenIssue {
  number: number;
  title: string;
  labels: string[]; // all label names on this issue
}

export type BucketName =
  | "built-this-run" // implemented + reviewed + PR opened this run
  | "repaired-sweep-pr" // stranded branch injected by sweep; PR opened this run
  | "repaired-sweep-requeued" // stranded; no branch → relabeled ready-for-agent
  | "human-gated-pr" // in-review with an open PR (from a previous run)
  | "human-gated-ready-for-human" // handed off to human
  | "human-gated-untriaged" // open, no lifecycle label
  | "human-gated-delivered-parent" // open parent; every child closed → ready to close
  | "in-flight-needs-review" // implemented; reviewer errored; pending re-review
  | "ready-for-agent" // queued for agent; may be blocked by dependencies
  | "blocked-parent-conflict" // ≥2 parents conflict; needs a human merge (#64)
  | "retired-gate-failure" // failed the full-suite gate at the cap → human (#25)
  | "uncategorized"; // BUG: should not happen

export interface BucketedIssue {
  number: number;
  title: string;
  bucket: BucketName;
  prNumber?: number; // set for built-this-run / repaired-sweep-pr
  blockedParents?: string[]; // conflicting parent ids, for blocked-parent-conflict
  gateFailure?: string; // failing-test tail, for retired-gate-failure (#25)
}

const HUMAN_GATED_BUCKETS = new Set<BucketName>([
  "human-gated-pr",
  "human-gated-ready-for-human",
  "human-gated-untriaged",
  // A fully-delivered parent only a human can close (the bot never closes an
  // issue) — gated on a human, so "nothing left for the bot" stays accurate.
  "human-gated-delivered-parent",
  // A parent-conflict block needs a human to merge the parents — from the bot's
  // view it is gated on a human, so "nothing left for the bot" stays accurate.
  "blocked-parent-conflict",
  // A gate-retired set is parked on a human (ready-for-human); the bot won't
  // touch it again this or next run, so it counts as human-gated too (#25).
  "retired-gate-failure",
]);
const IN_FLIGHT_BUCKETS = new Set<BucketName>(["in-flight-needs-review"]);

// A sub-issue edge: every issue's own state plus its native GitHub parent (null
// if it has none). Fed from an all-state fetch so closed children are visible.
export interface IssueEdge {
  number: number;
  state: "OPEN" | "CLOSED";
  parent: number | null;
}

// The set of parent ids (as strings) that are open while every one of their
// sub-issues is closed — a spec fully delivered, its umbrella issue lingering.
// Pure so it is unit-tested; the gh fetch that feeds it lives in main.mts.
export function deliveredParentIds(edges: IssueEdge[]): Set<string> {
  const stateById = new Map<number, "OPEN" | "CLOSED">();
  const childStates = new Map<number, ("OPEN" | "CLOSED")[]>();
  for (const e of edges) {
    stateById.set(e.number, e.state);
    if (e.parent !== null) {
      const kids = childStates.get(e.parent) ?? [];
      kids.push(e.state);
      childStates.set(e.parent, kids);
    }
  }
  const delivered = new Set<string>();
  for (const [parent, states] of childStates) {
    if (
      stateById.get(parent) === "OPEN" &&
      states.every((s) => s === "CLOSED")
    ) {
      delivered.add(String(parent));
    }
  }
  return delivered;
}

export function bucketIssues(options: {
  openIssues: OpenIssue[];
  // issue ids (as strings) completed this run — includes sweep-injected
  builtThisRun: Set<string>;
  // subset of builtThisRun that came from the sweep (stranded branch)
  sweepInjected: Set<string>;
  // issue ids relabeled ready-for-agent by the sweep (no-branch case)
  sweepRequeued: Set<string>;
  // issue id → PR number, set during Phase 3
  prAssignments: Map<string, number>;
  // issue id → conflicting parent ids: aborted this run because its multi-parent
  // base could not be built (#64). Still carries its ready-for-agent label, so it
  // must be caught before the label buckets below.
  blockedByParentConflict: Map<string, string[]>;
  // issue id → bounded failing-test tail: the set was retired by the Phase-3
  // consecutive gate-failure cap (#25). Relabeled ready-for-human AND completed
  // (in builtThisRun), so it must be caught before both those buckets below.
  retiredByGate: Map<string, string>;
  // parent issue ids (as strings) that are open with ≥1 sub-issue, all closed:
  // the spec is delivered and only its umbrella issue lingers. Caught before the
  // label buckets so a spent parent carrying a stray label (e.g. ready-for-human)
  // still surfaces as ready-to-close rather than hiding behind that label.
  deliveredParents: Set<string>;
}): BucketedIssue[] {
  return options.openIssues.map((issue) => {
    const id = String(issue.number);
    const labelSet = new Set(issue.labels);
    const prNumber = options.prAssignments.get(id);

    const blockedParents = options.blockedByParentConflict.get(id);
    if (blockedParents) {
      return {
        number: issue.number,
        title: issue.title,
        bucket: "blocked-parent-conflict",
        blockedParents,
      };
    }

    // Retired by the gate cap (#25): caught before builtThisRun and the
    // ready-for-human label bucket, both of which it would otherwise match.
    const gateFailure = options.retiredByGate.get(id);
    if (gateFailure != null) {
      return {
        number: issue.number,
        title: issue.title,
        bucket: "retired-gate-failure",
        gateFailure,
      };
    }

    // A requeued-but-not-PR'd issue reports re-queued. Requeue happens two ways:
    // up front in the sweep (stale branch deleted) or post-Phase-3 (its merge
    // conflicted). Either may also sit in builtThisRun. Gate on prNumber: if the
    // run went on to rebuild it and open a PR, report THAT (fall through to
    // built-this-run below) — only a genuinely PR-less requeue is "re-queued".
    if (options.sweepRequeued.has(id) && prNumber == null) {
      return {
        number: issue.number,
        title: issue.title,
        bucket: "repaired-sweep-requeued",
      };
    }

    if (options.builtThisRun.has(id)) {
      // Only claim a sweep repair "PR opened" when a PR actually landed.
      const bucket =
        options.sweepInjected.has(id) && prNumber != null
          ? "repaired-sweep-pr"
          : "built-this-run";
      return { number: issue.number, title: issue.title, bucket, prNumber };
    }

    // A delivered parent (open, every sub-issue closed) surfaces as ready-to-
    // close before any label bucket: a spent spec often still carries a stray
    // lifecycle label, and the close reminder must win over it.
    if (options.deliveredParents.has(id))
      return {
        number: issue.number,
        title: issue.title,
        bucket: "human-gated-delivered-parent",
      };

    if (labelSet.has("in-review"))
      return {
        number: issue.number,
        title: issue.title,
        bucket: "human-gated-pr",
      };

    if (labelSet.has("ready-for-human"))
      return {
        number: issue.number,
        title: issue.title,
        bucket: "human-gated-ready-for-human",
      };

    if (labelSet.has("needs-review"))
      return {
        number: issue.number,
        title: issue.title,
        bucket: "in-flight-needs-review",
      };

    if (labelSet.has("ready-for-agent"))
      return {
        number: issue.number,
        title: issue.title,
        bucket: "ready-for-agent",
      };

    // No lifecycle label → untriaged.
    return {
      number: issue.number,
      title: issue.title,
      bucket: "human-gated-untriaged",
    };
  });
}

export function buildRunSummary(bucketed: BucketedIssue[]): string {
  const sections: string[] = ["\n=== Run Summary ===\n"];

  const byBucket = new Map<BucketName, BucketedIssue[]>();
  for (const issue of bucketed) {
    if (!byBucket.has(issue.bucket)) byBucket.set(issue.bucket, []);
    byBucket.get(issue.bucket)!.push(issue);
  }

  const renderIssues = (items: BucketedIssue[], prSuffix = false) =>
    items
      .map((i) => {
        const pr = prSuffix && i.prNumber != null ? ` → PR #${i.prNumber}` : "";
        // For a parent-conflict block, name the parents a human must merge.
        const blocked = i.blockedParents?.length
          ? ` — parents ${i.blockedParents
              .map((p) => `#${p}`)
              .join(", ")} conflict; merge upstream first`
          : "";
        return `  #${i.number} — ${i.title}${pr}${blocked}`;
      })
      .join("\n");

  const section = (label: string, bucket: BucketName, prSuffix = false) => {
    const items = byBucket.get(bucket) ?? [];
    if (items.length === 0) return;
    sections.push(
      `${label} (${items.length}):\n${renderIssues(items, prSuffix)}`
    );
  };

  section("Built this run", "built-this-run", true);
  section("Repaired by sweep (PR opened)", "repaired-sweep-pr", true);
  section("Repaired by sweep (re-queued)", "repaired-sweep-requeued");
  section("Human-gated: open PR pending merge", "human-gated-pr");
  section("Human-gated: ready for human", "human-gated-ready-for-human");

  // Gate-retired sets (#25): name the set AND its failing tests, so the human
  // sees what broke without opening the issue. Custom render — the generic
  // section() helper drops the gateFailure tail.
  const retired = byBucket.get("retired-gate-failure") ?? [];
  if (retired.length > 0) {
    const items = retired
      .map((i) => {
        const tail = i.gateFailure?.trim();
        const failing = tail
          ? "\n" +
            tail
              .split("\n")
              .map((l) => `      ${l}`)
              .join("\n")
          : "";
        return `  #${i.number} — ${i.title}${failing}`;
      })
      .join("\n");
    sections.push(
      `Retired: full-suite gate failed ${retired.length > 1 ? "these sets" : "at the cap"} → ready-for-human (${retired.length}):\n${items}`
    );
  }
  section(
    "Human-gated: untriaged (needs ready-for-agent)",
    "human-gated-untriaged"
  );
  section(
    "Human-gated: delivered (every child closed — ready to close)",
    "human-gated-delivered-parent"
  );
  section("In-flight: needs-review", "in-flight-needs-review");
  section(
    "Blocked: parent conflict (human must merge parents)",
    "blocked-parent-conflict"
  );
  section("Available (queued / blocked)", "ready-for-agent");

  const bugs = byBucket.get("uncategorized") ?? [];
  if (bugs.length > 0) {
    sections.push(
      `BUG — uncategorized issues (should never happen) (${bugs.length}):\n${renderIssues(bugs)}`
    );
  }

  const nonHumanNonFlight = bucketed.filter(
    (i) =>
      !HUMAN_GATED_BUCKETS.has(i.bucket) && !IN_FLIGHT_BUCKETS.has(i.bucket)
  );

  if (nonHumanNonFlight.length === 0) {
    sections.push(
      "All open issues are human-gated or in-flight. Nothing left for the bot."
    );
  }

  return sections.join("\n");
}
