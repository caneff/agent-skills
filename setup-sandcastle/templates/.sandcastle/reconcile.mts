// Pure functions for reconciliation sweep and bucketed run summary.
//
// classifyInReviewIssue: classify a single in-review issue based on its PRs.
// bucketIssues: bucket all open issues for the end-of-run summary.
// buildRunSummary: format the bucketed summary as a printable string.

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
  | "in-flight-needs-review" // implemented; reviewer errored; pending re-review
  | "ready-for-agent" // queued for agent; may be blocked by dependencies
  | "uncategorized"; // BUG: should not happen

export interface BucketedIssue {
  number: number;
  title: string;
  bucket: BucketName;
  prNumber?: number; // set for built-this-run / repaired-sweep-pr
}

const HUMAN_GATED_BUCKETS = new Set<BucketName>([
  "human-gated-pr",
  "human-gated-ready-for-human",
  "human-gated-untriaged",
]);
const IN_FLIGHT_BUCKETS = new Set<BucketName>(["in-flight-needs-review"]);

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
}): BucketedIssue[] {
  return options.openIssues.map((issue) => {
    const id = String(issue.number);
    const labelSet = new Set(issue.labels);
    const prNumber = options.prAssignments.get(id);

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
  section("Repaired by sweep (PR opened)", "repaired-sweep-pr", true);
  section("Repaired by sweep (re-queued)", "repaired-sweep-requeued");
  section("Human-gated: open PR pending merge", "human-gated-pr");
  section("Human-gated: ready for human", "human-gated-ready-for-human");
  section(
    "Human-gated: untriaged (needs ready-for-agent)",
    "human-gated-untriaged"
  );
  section("In-flight: needs-review", "in-flight-needs-review");
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
