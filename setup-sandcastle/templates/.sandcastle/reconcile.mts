// Pure functions for the bucketed run summary.
//
// bucketIssues: bucket all open issues for the end-of-run summary.
// buildRunSummary: format the bucketed summary as a printable string.
//
// The outcome→label transition (planOutcomeTransition, OutcomeKind,
// OutcomePlan, OutcomeIssue) moved to issue-lifecycle.mts — the lifecycle
// vocabulary's one home.

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

// The set of parent numbers that are open while every one of their sub-issues
// is closed — a spec fully delivered, its umbrella issue lingering. Pure so it
// is unit-tested; the gh fetch that feeds it lives in main.mts.
export function deliveredParentIds(edges: IssueEdge[]): Set<number> {
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
  const delivered = new Set<number>();
  for (const [parent, states] of childStates) {
    if (
      stateById.get(parent) === "OPEN" &&
      states.every((s) => s === "CLOSED")
    ) {
      delivered.add(parent);
    }
  }
  return delivered;
}

export function bucketIssues(options: {
  openIssues: OpenIssue[];
  // issue numbers that built to a clean review and opened a PR this run
  builtThisRun: Set<number>;
  // issue number → PR number, set when its PR opened
  prAssignments: Map<number, number>;
  // parent issue numbers that are open with ≥1 sub-issue, all closed: the spec
  // is delivered and only its umbrella issue lingers. Caught before the label
  // buckets so a spent parent carrying a stray label (e.g. ready-for-human)
  // still surfaces as ready-to-close rather than hiding behind that label.
  deliveredParents: Set<number>;
}): BucketedIssue[] {
  return options.openIssues.map((issue) => {
    const labelSet = new Set(issue.labels);
    const prNumber = options.prAssignments.get(issue.number);

    if (options.builtThisRun.has(issue.number)) {
      return {
        number: issue.number,
        title: issue.title,
        bucket: "built-this-run",
        prNumber,
      };
    }

    if (options.deliveredParents.has(issue.number))
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

// A review-fail carries its failing axes and a one-line why (the first failed
// axis's reason, truncated to one line by the caller) plus the preserved
// branch a human re-drives with /implement. An error is a harness/sandbox
// crash or a reviewer error — main.mts leaves the issue's labels untouched
// either way, so the wording is shared, content-blind of the actual cause.
export interface StuckReviewFail {
  kind: "review-fail";
  number: number;
  title: string;
  failedAxes: string[];
  why?: string;
  branch: string;
}

export interface StuckError {
  kind: "error";
  number: number;
  title: string;
}

export type StuckIssue = StuckReviewFail | StuckError;

// An open, not-built-this-run issue reachable (directly or transitively) from a
// failed issue along blockedBy edges. waitsOn is its own immediate blocker —
// the failed issue itself, or a dammed issue between it and the failed root.
export interface DammedIssue {
  number: number;
  title: string;
  waitsOn: number;
}

// One merge line for the copy-paste Next footer, already in base-first order.
export interface NextMerge {
  pr: number;
  issue: number;
  note?: string;
  // The parent issue number this child is stacked on, when the PR's base is
  // another PR built this run. Absent for a root/independent PR.
  stackedOn?: number;
}

// The run-scoped extras buildRunSummary layers onto the bucketed sections.
// Every field is optional so the 1-arg call (no run this pass) simply omits
// the blocks.
export interface RunExtras {
  stuck?: StuckIssue[];
  dammed?: DammedIssue[];
  nextMerges?: NextMerge[];
}

function renderStuck(items: StuckIssue[]): string {
  return items
    .map((item) => {
      if (item.kind === "review-fail") {
        const axisLine = item.why
          ? `${item.failedAxes[0] ?? "review"}: ${item.why}`
          : item.failedAxes.join(", ");
        return [
          `  [review-fail] #${item.number} — ${item.title}`,
          `      ${axisLine}`,
          `      branch ${item.branch} pushed; review notes written to the issue.`,
          `      → re-drive:  /implement #${item.number}   (continues the branch, see issue body)`,
        ].join("\n");
      }
      return [
        `  [error]       #${item.number} — ${item.title}`,
        `      sandbox failed to launch (harness). Labels untouched —`,
        `      picked up as a fresh attempt next run. No action needed unless it repeats.`,
      ].join("\n");
    })
    .join("\n\n");
}

function renderDammed(items: DammedIssue[]): string {
  return items
    .map((i) => `  #${i.number} — ${i.title}   (waits on #${i.waitsOn})`)
    .join("\n");
}

function renderNextFooter(nextMerges: NextMerge[]): string {
  const lines = nextMerges.flatMap((m) => {
    const mergeLine = `  gh pr merge ${m.pr} --squash --delete-branch    # #${
      m.issue
    }${m.note ? `, ${m.note}` : ""}`;
    if (m.stackedOn == null) return [mergeLine];
    return [
      mergeLine,
      `      if #${m.stackedOn} bounces: merge the fixed/reworked parent to`,
      `      main, then git rebase this child (#${m.issue}) onto main —`,
      `      a small parent change usually applies clean and refreshes the`,
      `      child PR with zero agent work.`,
      `      only on a rebase conflict: /implement #${m.issue}   (re-drives`,
      `      the child on its preserved branch to resolve)`,
    ];
  });
  lines.push(
    `  /sandcastle-watch                           # re-run to continue the drain`
  );
  return `Next — copy-paste, bottom-up:\n${lines.join("\n")}`;
}

// Topologically order a run's built issues so a PR whose base is another PR
// built this run always comes after that base's merge line. Roots and
// independents (baseParent null, or not itself in the built set) keep their
// input order — a stable sort on depth alone. Private helper of buildNextMerges.
function orderMergesBaseFirst(
  built: Array<{ issue: number; pr: number; baseParent: number | null }>
): Array<{ issue: number; pr: number }> {
  const byIssue = new Map(built.map((b) => [b.issue, b]));
  const depthCache = new Map<number, number>();
  const depth = (issue: number): number => {
    const cached = depthCache.get(issue);
    if (cached !== undefined) return cached;
    const item = byIssue.get(issue);
    const d =
      item && item.baseParent !== null && byIssue.has(item.baseParent)
        ? depth(item.baseParent) + 1
        : 0;
    depthCache.set(issue, d);
    return d;
  };
  return built
    .map((b, i) => ({ b, i, d: depth(b.issue) }))
    .sort((x, y) => x.d - y.d || x.i - y.i)
    .map(({ b }) => ({ issue: b.issue, pr: b.pr }));
}

// Assemble the base-first Next-footer merge lines for everything built this run.
// baseParent is an issue's single native parent that also built this run — the
// same relation resolveBase used to pick the branch's base. Two built parents
// (a diamond) means no single branch to stack on, so the child bases on main:
// baseParent null, note "independent". A built issue used as someone's base is
// "base of the stack"; one stacked on a parent carries stackedOn for the
// two-tier rebase recipe.
export function buildNextMerges(
  prAssignments: Map<number, number>,
  blockedBy: Map<number, number[]>,
  builtIds: Set<number>
): NextMerge[] {
  const builtForMerges = [...prAssignments.entries()].map(([issue, pr]) => {
    const builtParents = (blockedBy.get(issue) ?? []).filter((p) =>
      builtIds.has(p)
    );
    return { issue, pr, baseParent: builtParents.length === 1 ? builtParents[0]! : null };
  });
  const usedAsBase = new Set(
    builtForMerges.map((b) => b.baseParent).filter((p): p is number => p !== null)
  );
  const mergeInfoByIssue = new Map(builtForMerges.map((b) => [b.issue, b]));
  return orderMergesBaseFirst(builtForMerges).map(({ issue, pr }) => {
    const entry = mergeInfoByIssue.get(issue)!;
    const note =
      entry.baseParent !== null
        ? `stacked on #${entry.baseParent}`
        : usedAsBase.has(issue)
          ? "base of the stack"
          : "independent";
    return { pr, issue, note, stackedOn: entry.baseParent ?? undefined };
  });
}

// An open, not-built-this-run issue is dammed if any of its blockedBy edges is
// itself in failedThisRun, OR is itself dammed (reachable transitively along
// blockedBy back to a failed root). waitsOn is the immediate blocker that made
// it dammed — the failed issue for a direct child, the dammed parent (not the
// failed grandparent) for a grandchild.
export function deriveDammed(
  openIssues: OpenIssue[],
  blockedBy: Map<number, number[]>,
  failedThisRun: Set<number>,
  builtThisRun: Set<number>
): DammedIssue[] {
  const waitsOnCache = new Map<number, number | null>();

  const resolve = (issueNumber: number, seen: Set<number>): number | null => {
    const cached = waitsOnCache.get(issueNumber);
    if (cached !== undefined) return cached;
    if (seen.has(issueNumber)) return null; // cycle guard
    seen.add(issueNumber);

    const blockers = blockedBy.get(issueNumber) ?? [];
    for (const b of blockers) {
      if (failedThisRun.has(b)) {
        waitsOnCache.set(issueNumber, b);
        return b;
      }
    }
    for (const b of blockers) {
      if (resolve(b, seen) !== null) {
        waitsOnCache.set(issueNumber, b);
        return b;
      }
    }
    waitsOnCache.set(issueNumber, null);
    return null;
  };

  const result: DammedIssue[] = [];
  for (const issue of openIssues) {
    if (builtThisRun.has(issue.number)) continue;
    const waitsOn = resolve(issue.number, new Set());
    if (waitsOn !== null) {
      result.push({ number: issue.number, title: issue.title, waitsOn });
    }
  }
  return result;
}

export function buildRunSummary(
  bucketed: BucketedIssue[],
  run: RunExtras = {}
): string {
  const sections: string[] = ["\n=== Run Summary ===\n"];

  // A stuck or dammed issue still carries whatever label the earlier phases
  // left it with (ready-for-human for a review-fail, ready-for-agent for a
  // dammed child) — bucketIssues has no way to know either happened, so it
  // buckets them same as any other open issue. Drop those numbers from the
  // bucketed sections here so each issue renders exactly once: under Stuck or
  // Dammed, never also under a stale human-gated/available bucket.
  const stuckOrDammed = new Set<number>([
    ...(run.stuck ?? []).map((s) => s.number),
    ...(run.dammed ?? []).map((d) => d.number),
  ]);
  const effectiveBucketed =
    stuckOrDammed.size > 0
      ? bucketed.filter((b) => !stuckOrDammed.has(b.number))
      : bucketed;

  const byBucket = new Map<BucketName, BucketedIssue[]>();
  for (const issue of effectiveBucketed) {
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

  const stuck = run.stuck ?? [];
  if (stuck.length > 0) {
    sections.push(`Stuck — needs you (${stuck.length}):\n${renderStuck(stuck)}`);
  }

  const dammed = run.dammed ?? [];
  if (dammed.length > 0) {
    sections.push(
      `Dammed behind a failure (${dammed.length}):\n${renderDammed(dammed)}`
    );
  }

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

  const nonHumanGated = effectiveBucketed.filter(
    (i) => !HUMAN_GATED_BUCKETS.has(i.bucket)
  );

  if (nonHumanGated.length === 0) {
    sections.push(
      "All open issues are human-gated. Nothing left for the bot."
    );
  }

  const nextMerges = run.nextMerges ?? [];
  if (nextMerges.length > 0) {
    sections.push(renderNextFooter(nextMerges));
  }

  return sections.join("\n");
}
