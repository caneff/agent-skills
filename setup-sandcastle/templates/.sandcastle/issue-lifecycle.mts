// Issue-lifecycle vocabulary: the shared vocabulary for what happened to an
// issue's build, and what the run does about it.
//
// Consolidates what used to be smeared across four files — the
// done|review-fail|nothing union (review-verdict.mts's ReviewedOutcome,
// re-unioned as pipeline-results.mts's IssueOutcome), ReviewAxis
// (review-verdict.mts), the outcome→label transition (reconcile.mts's
// planOutcomeTransition/OutcomeKind/OutcomePlan), and the failure-section
// splice (formerly in issue-body.mts) — into one module.
// Adding a new outcome kind, or changing what the lifecycle does, now happens
// in exactly one place.

// The two axes a review judges independently.
export type ReviewAxis = "spec" | "standards";

// The terminal outcome of a reviewed branch: cleared on both axes, or failed
// with the axes named. A review-fail carries each failed axis's fuller reviewer
// stdout — the brief a human re-drives the preserved branch from.
export type ReviewedOutcome =
  | { kind: "done" }
  | {
      kind: "review-fail";
      failedAxes: ReviewAxis[];
      reasons: Partial<Record<ReviewAxis, string>>;
    };

// One issue's terminal outcome, generic over the issue shape so this module
// stays decoupled from main's WorkIssue. `done`/`review-fail` are the reviewed
// outcomes above — reused here, not restated; `nothing` (labels left as they
// arrived) is the only kind this stage adds.
export type IssueOutcome<I> = { issue: I } & (
  | ReviewedOutcome
  | { kind: "nothing" }
);

export type OutcomeKind = "done" | "review-fail" | "nothing";

// The issue as the execute loop knows it — from the planner, carrying its forest
// position (parents) and topic group. (parents and group are vestigial in the
// one-PR-per-issue model — carried through, not acted on — but kept so the plan
// item and this type are one shape.)
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
  // spliceReviewFailureSection, or planFailureBodyEdit below) — the failing
  // axes, why, and how to continue the preserved branch. Absent otherwise.
  failureSection?: string;
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
      // Titled block, not an inline bullet: the reviewer's report can run many
      // lines, so it sits on its own lines under the bolded axis rather than
      // trailing an em dash where a multi-line report would break the list.
      return why ? `**${axis}**\n\n${why}` : `**${axis}**`;
    })
    .join("\n\n");
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

// -----------------------------------------------------------------------------
// The failure-section splice.
//
// When a two-axis review fails, the orchestrator writes the failure context
// (which axis, why, how to continue the preserved branch) INTO the issue body
// so a human re-driving it with `/implement` reads the instruction as part of
// its brief (#240 story 15a). That write is a read-modify-write: the section is
// fenced by two HTML-comment markers — invisible in rendered markdown, exact to
// match — so a re-run REPLACES the block in place rather than stacking a second
// copy, and the original spec text is never touched.
// -----------------------------------------------------------------------------

export const REVIEW_FAILURE_BEGIN = "<!-- sandcastle:review-failure -->";
export const REVIEW_FAILURE_END = "<!-- /sandcastle:review-failure -->";

// Return `body` with `section` fenced between the markers: replacing an existing
// fenced block if one is present, appending it (separated by a blank line) if
// not. Pure string→string; the caller does the `gh issue edit`.
export function spliceReviewFailureSection(
  body: string,
  section: string
): string {
  const block = `${REVIEW_FAILURE_BEGIN}\n${section}\n${REVIEW_FAILURE_END}`;

  const start = body.indexOf(REVIEW_FAILURE_BEGIN);
  const end = body.indexOf(REVIEW_FAILURE_END);
  if (start !== -1 && end !== -1 && end > start) {
    // Replace in place; keep everything before the opening marker and after the
    // closing one (a human may have written notes below our block).
    return body.slice(0, start) + block + body.slice(end + REVIEW_FAILURE_END.length);
  }

  const trimmed = body.replace(/\s+$/, "");
  return trimmed.length ? `${trimmed}\n\n${block}\n` : `${block}\n`;
}

// The read-modify-write's "modify" step, lifted out of main's Phase 3 loop so
// it's pure and unit-tested. `gh issue view` can return null on a transient
// fetch error — that must never be turned into a write that clobbers the
// ticket with ONLY the failure section, so a null body plans a skip instead of
// an edit. The caller (main.mts.jinja) does the `gh` read and the
// `editIssueBody` write; this only decides.
export type FailureBodyEdit = { kind: "edit"; body: string } | { kind: "skip" };

export function planFailureBodyEdit(
  body: string | null,
  failureSection: string
): FailureBodyEdit {
  if (body === null) return { kind: "skip" };
  return { kind: "edit", body: spliceReviewFailureSection(body, failureSection) };
}
