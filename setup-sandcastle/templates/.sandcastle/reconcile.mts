// Pure functions for the outcome→label engine and the bucketed run summary.
//
// planOutcomeTransition: decide one issue's terminal labels from its build outcome.
// bucketIssues: bucket all open issues for the end-of-run summary.
// buildRunSummary: format the bucketed summary as a printable string.

import type { ReviewAxis } from "./review-verdict.mts";

// One issue the run built to a clean review — its identity and the branch its PR
// is cut from. (Formerly in pr-components.mts, which the one-PR-per-issue rewrite
// deleted; the record survives because the run summary counts what was built.)
export interface CompletedIssue {
  id: string;
  title: string;
  branch: string;
  // Carried through from the planner but no longer used for PR grouping — one
  // issue is one PR. Kept so the planner's work item and this record stay one
  // shape.
  parents: string[];
  group?: string;
}

// What the execute+review pipeline concluded for one issue.
//   done        — implemented and reviewed clean on both axes; open its PR.
//   review-fail — reviewed, but a review axis (spec and/or standards) failed;
//                 `failedAxes` names which. Binding: no PR, handed to a human.
//   nothing     — no work happened: the branch has no diff vs main, or main.mts
//                 mapped a rejected pipeline (sandbox crash, network) here.
export type OutcomeKind = "done" | "review-fail" | "nothing";

// The issue as the execute loop knows it — from the planner, carrying its forest
// position (parents) and topic group. (parents and group are vestigial in the
// one-PR-per-issue model — carried through, not acted on — but kept so the plan
// item, this type, and CompletedIssue are one shape.)
export interface OutcomeIssue {
  id: string;
  title: string;
  branch: string;
  parents: string[];
  group?: string;
}

export interface OutcomePlan {
  // Label to add, or null when the outcome touches no label at all.
  addLabel: string | null;
  removeLabels: string[];
  // review-fail only: keep and push the work branch so the human inherits the
  // actual failing tree, not a deleted branch.
  preserveBranch: boolean;
  // review-fail only: the section to splice into the issue body (via
  // spliceReviewFailureSection) — the failing axes, why, and how to continue the
  // preserved branch. Absent otherwise.
  failureSection?: string;
  // done only: the record main.mts accumulates for the run summary.
  completed?: CompletedIssue;
  // Operator-facing line main.mts prints, unindented — the caller owns layout.
  // Absent when there is nothing to say.
  note?: string;
}

// The review-failure section written into the issue body. It names the failing
// axes and, per axis, the reviewer's reason, then tells a human how to re-drive
// the ticket with `/implement`: continue the PRESERVED branch via
// `git worktree add` (not `EnterWorktree`, which only branches fresh from main).
function reviewFailureSection(
  issue: OutcomeIssue,
  failedAxes: ReviewAxis[] | undefined,
  reasons: Partial<Record<ReviewAxis, string>> | undefined
): string {
  const axes = failedAxes?.length ? failedAxes : (["review"] as const);
  const failing = axes
    .map((axis) => {
      const why = reasons?.[axis as ReviewAxis];
      return why ? `- **${axis}** — ${why}` : `- **${axis}**`;
    })
    .join("\n");
  return [
    "## ⚠️ Sandcastle review failed — continue this branch, don't rebuild",
    "",
    "The two-axis review did not pass, so no PR was opened. The work branch " +
      `\`${issue.branch}\` is preserved (pushed) — pick it up rather than starting over.`,
    "",
    "**Failing:**",
    failing,
    "",
    `**To continue:** run \`/implement ${issue.id}\` — it reads this ticket as its ` +
      "brief. Address the points above on the PRESERVED branch; do not branch fresh " +
      "from `main`. Check it out with:",
    "",
    "```sh",
    `git worktree add ../issue-${issue.id} ${issue.branch}`,
    "```",
  ].join("\n");
}

export function planOutcomeTransition(input: {
  kind: OutcomeKind;
  issue: OutcomeIssue;
  // The review axes that failed, for a review-fail outcome — names the axis in
  // the note and the failure section. Absent otherwise.
  failedAxes?: ReviewAxis[];
  // Per-axis reason from the combined verdict, embedded in the failure section
  // so the human sees why without opening the run log. Absent otherwise.
  reasons?: Partial<Record<ReviewAxis, string>>;
}): OutcomePlan {
  const { kind, issue, failedAxes, reasons } = input;

  if (kind === "done") {
    return {
      addLabel: "in-review",
      removeLabels: ["ready-for-agent"],
      preserveBranch: false,
      completed: {
        id: issue.id,
        title: issue.title,
        branch: issue.branch,
        parents: issue.parents,
        ...(issue.group ? { group: issue.group } : {}),
      },
    };
  }

  if (kind === "review-fail") {
    // Binding, no retry: a failing axis routes straight to a human. The branch
    // is preserved and pushed, and the reasons are written into the issue body
    // so `/implement` can re-drive it from where it stands.
    const axes = failedAxes?.length ? failedAxes.join(", ") : "review";
    return {
      addLabel: "ready-for-human",
      removeLabels: ["ready-for-agent"],
      preserveBranch: true,
      failureSection: reviewFailureSection(issue, failedAxes, reasons),
      note: `${issue.id} failed review (${axes}); no PR — branch preserved, handed to a human (ready-for-human)`,
    };
  }

  // "nothing": no work was produced, a verdict on the run, not the branch. Leave
  // the issue exactly as it arrived — it keeps ready-for-agent and is a fresh
  // single attempt next run.
  return { addLabel: null, removeLabels: [], preserveBranch: false };
}

export interface OpenIssue {
  number: number;
  title: string;
  labels: string[]; // all label names on this issue
}

export type BucketName =
  | "built-this-run" // implemented + reviewed + PR opened this run
  | "human-gated-pr" // in-review with an open PR (from a previous run)
  | "human-gated-ready-for-human" // handed off to human
  | "human-gated-untriaged" // open, no lifecycle label
  | "human-gated-delivered-parent" // open parent; every child closed → ready to close
  | "ready-for-agent" // queued for agent; may be blocked by dependencies
  | "uncategorized"; // BUG: should not happen

export interface BucketedIssue {
  number: number;
  title: string;
  bucket: BucketName;
  prNumber?: number; // set for built-this-run
}

const HUMAN_GATED_BUCKETS = new Set<BucketName>([
  "human-gated-pr",
  "human-gated-ready-for-human",
  "human-gated-untriaged",
  // A fully-delivered parent only a human can close (the bot never closes an
  // issue) — gated on a human, so "nothing left for the bot" stays accurate.
  "human-gated-delivered-parent",
]);

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
  // issue ids (as strings) that built to a clean review and opened a PR this run
  builtThisRun: Set<string>;
  // issue id → PR number, set when its PR opened
  prAssignments: Map<string, number>;
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

    if (options.builtThisRun.has(id)) {
      return {
        number: issue.number,
        title: issue.title,
        bucket: "built-this-run",
        prNumber,
      };
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
        return `  #${i.number} — ${i.title}${pr}`;
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
  section("Human-gated: open PR pending merge", "human-gated-pr");
  section("Human-gated: ready for human", "human-gated-ready-for-human");
  section(
    "Human-gated: untriaged (needs ready-for-agent)",
    "human-gated-untriaged"
  );
  section(
    "Human-gated: delivered (every child closed — ready to close)",
    "human-gated-delivered-parent"
  );
  section("Available (queued / blocked)", "ready-for-agent");

  const bugs = byBucket.get("uncategorized") ?? [];
  if (bugs.length > 0) {
    sections.push(
      `BUG — uncategorized issues (should never happen) (${bugs.length}):\n${renderIssues(bugs)}`
    );
  }

  const nonHumanGated = bucketed.filter(
    (i) => !HUMAN_GATED_BUCKETS.has(i.bucket)
  );

  if (nonHumanGated.length === 0) {
    sections.push(
      "All open issues are human-gated. Nothing left for the bot."
    );
  }

  return sections.join("\n");
}
