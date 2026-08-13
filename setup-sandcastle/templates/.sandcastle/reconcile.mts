// Pure functions for the bucketed run summary.
//
// bucketIssues: bucket all open issues for the end-of-run summary.
// buildRunSummary: format the bucketed summary as a printable string.
//
// The outcome→label transition (planOutcomeTransition, OutcomeKind,
// OutcomePlan, OutcomeIssue, CompletedIssue) moved to issue-lifecycle.mts —
// the lifecycle vocabulary's one home.

export interface OpenIssue {
  number: number;
  title: string;
  labels: string[];
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
