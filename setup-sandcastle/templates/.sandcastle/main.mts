// Parallel Planner with Review — dependency-forest orchestration loop
//
// This template drives a multi-phase workflow:
//   Phase 1 (Plan):             An opus agent analyzes open issues, builds a
//                               dependency graph, and outputs a <plan> JSON
//                               listing unblocked issues with branch names AND
//                               the `parents` each one builds on.
//   Phase 2 (Execute + Review): For each issue, a sandbox is created via
//                               createSandbox(), cut from its RESOLVED BASE — its
//                               parent's branch when it has one present this run,
//                               otherwise `main`. Chains are independent off main
//                               (the forest); a child branch carries its parent's
//                               commits but never an unrelated chain's. The
//                               implementer runs first (100 iterations); if
//                               there's work on the branch two read-only judges
//                               (Spec + Standards) run in the same sandbox (1
//                               iteration each), committing nothing. All issue
//                               pipelines run concurrently via
//                               Promise.allSettled().
//   Phase 3 (Open PRs):         The host splits the run's completed issues into
//                               connected dependency components and opens ONE PR
//                               per component: it merges each component's leaf
//                               tips into a throwaway head off `main`,
//                               force-pushes it, and an agent opens the PR into
//                               main for manual review (no auto-merge).
//
// The outer loop repeats up to MAX_ITERATIONS times. Because a completed issue's
// branch is immutable and the next iteration's dependent branches are cut from
// it directly (base resolution), an issue blocked by an earlier one is picked up
// and built on top once the earlier one lands — instead of deadlocking until a
// human merges. There is no single integration tip and no per-issue fold: the
// forest replaces the former one revisable stack.
//
// PRs are split by PR set (one run → several PRs): a connected component of
// dependency edges, with independent same-topic components combined via a `group`
// key the planner emits. A multi-parent (diamond) issue is built on a temp base
// branch merging all its parents.
//
// Usage:
//   npx tsx .sandcastle/main.mts
// Or add to package.json:
//   "scripts": { "sandcastle": "npx tsx .sandcastle/main.mts" }

import * as sandcastle from "@ai-hero/sandcastle";
import { addressOpenPRs } from "./address.mts";
import {
  sandboxIdentity,
  sandboxConfig,
  applyBotToken,
} from "./sandbox-identity.mts";
import {
  resolveBase,
  issueBranch,
  buildMultiParentBase,
} from "./base-resolution.mts";
import {
  prComponents,
  parentsFromBlockedBy,
  mergeParentEdges,
  landedIssues,
  CompletedIssue,
} from "./pr-components.mts";
import {
  parseSpecVerdict,
  parseStandardsVerdict,
  combineVerdicts,
  isHarnessError,
  parseCheckVerdict,
} from "./review-verdict.mts";
import {
  classifyInReviewIssue,
  decideInReviewAction,
  bucketIssues,
  buildRunSummary,
  planGateOutcome,
  planOutcomeTransition,
  OpenIssue,
  PrRef,
} from "./reconcile.mts";
import { parseOpenIssues, parsePrsClosingIssues } from "./github-parse.mts";
import { parseSandcastleWorktrees } from "./worktrees.mts";
import { planRetention } from "./log-retention.mts";
import {
  REVIEW_RETRY_CAP,
  readAttempts,
  writeAttempts,
  recordAttempt,
} from "./retry-policy.mts";
import { execSync } from "node:child_process";
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  existsSync,
  readdirSync,
  unlinkSync,
} from "node:fs";
import { z } from "zod";

// Sandcastle forwards .sandcastle/.env into sandboxes but never into the host
// process (it has no process.env assignment). sandboxIdentity() runs host-side
// and mints the bot token from GITHUB_APP_* — so without this, those vars are
// undefined on the host, minting no-ops, and PRs fall back to the personal
// GH_TOKEN. Load the env file here, before any sandboxIdentity() call.
if (existsSync(".sandcastle/.env")) process.loadEnvFile(".sandcastle/.env");

// ---------------------------------------------------------------------------
// Issue lifecycle labels (managed host-side, never by the agents)
//
//   ready-for-agent → fresh, plannable. The planner only ever selects these.
//   in-review       → implemented AND reviewed OK; PR pending a human merge.
//   needs-review    → implemented, but the reviewer errored. The branch keeps
//                     its commits; a later pass merges current main into the
//                     branch and re-runs ONLY the reviewer. After
//                     REVIEW_RETRY_CAP failed re-reviews it escalates back to
//                     ready-for-agent for a full re-implement.
//   ready-for-human → the reviewer found the branch doesn't meet the issue spec
//                     (#130) REVIEW_RETRY_CAP times; re-implementing isn't
//                     converging, so it's handed off for a human to take over.
//
// Transitioning out of ready-for-agent the moment an outcome is known (rather
// than at the very end of the run) is what stops a finished issue from being
// re-planned on the next iteration / next run.
// ---------------------------------------------------------------------------
function gh(args: string): string | null {
  try {
    return execSync(`gh ${args}`, {
      stdio: ["pipe", "pipe", "pipe"],
    })
      .toString()
      .trim();
  } catch {
    // Non-fatal: label already exists, label not on issue, transient API error.
    return null;
  }
}

function listIssues(label: string): { number: number; title: string }[] {
  const out = gh(
    `issue list --state open --label "${label}" --limit 100 --json number,title`
  );
  return out ? JSON.parse(out) : [];
}

function git(args: string): string | null {
  try {
    return execSync(`git ${args}`, { stdio: ["pipe", "pipe", "pipe"] })
      .toString()
      .trim();
  } catch {
    return null;
  }
}

// Write a Markdown body to a log file, then comment it on each issue with
// `--body-file` (not an inline `--body`) so a body with backticks or quotes
// can't break shell escaping. One place owns that file-not-shell-string choice.
function commentIssues(ids: string[], slug: string, body: string): void {
  const file = `.sandcastle/logs/${slug}.md`;
  writeFileSync(file, body);
  for (const id of ids) gh(`issue comment ${id} --body-file ${file}`);
}

// Log verbosity via SANDCASTLE_VERBOSE:
//   unset/0  quiet — parsed human-readable log only (drops tool-use blocks). Default.
//   1/2/full raw   — every raw stdout line verbatim (full firehose, interleaved)
const VERBOSE =
  process.env.SANDCASTLE_VERBOSE != null &&
  process.env.SANDCASTLE_VERBOSE !== "0";
mkdirSync(".sandcastle/logs", { recursive: true });

// Logs are append-only and gitignored. Sandcastle delimits each run with a
// `--- Run started: <ISO ts> ---` header, so we can keep just recent runs:
// drop everything before the first header newer than the cutoff. Runs at start,
// before this run logs, so the live run is never trimmed. Keeps stable filenames.
// A log with no run inside the window is emptied (all its runs are stale).
// ponytail: parse the header we already emit; no run-index/db needed.
const LOG_RETENTION_DAYS = 14;
// Thin file-IO caller; the keep/empty/keep-from decision lives in the pure,
// tested planRetention (ADR-0002).
function pruneOldRuns(dir: string, cutoffMs: number) {
  for (const name of readdirSync(dir)) {
    if (!name.endsWith(".log")) continue;
    const file = `${dir}/${name}`;
    const lines = readFileSync(file, "utf8").split("\n");
    const plan = planRetention(lines, cutoffMs);
    if (plan.action === "keep-all") continue; // already all-recent
    if (plan.action === "empty")
      unlinkSync(file); // no recent runs → drop the file
    else writeFileSync(file, lines.slice(plan.index).join("\n"));
  }
}
try {
  pruneOldRuns(
    ".sandcastle/logs",
    Date.now() - LOG_RETENTION_DAYS * 86_400_000
  );
} catch {}

// Build the per-run logging option, mirroring sandcastle's default filename
// (<sanitized-branch>-<name>.log under .sandcastle/logs/) so existing
// `tail -f` paths keep working, plus the chosen verbosity.
function logging(name: string, branch: string) {
  const sanitized = branch.replace(/[/\\:*?"<>|]/g, "-");
  const suffix = name.toLowerCase().replace(/[^a-z0-9_.-]/g, "-");
  const path = `.sandcastle/logs/${sanitized}-${suffix}.log`;
  return {
    type: "file" as const,
    path,
    verbose: VERBOSE,
  };
}

// Whether a branch carries real changes vs main — i.e. there is something to
// review and to put in a PR. Keyed on the diff, NOT on how many commits a given
// run produced: an implementer that resumes an already-complete branch makes
// zero new commits but the branch still has work. Three-dot diffs from the
// merge-base, so a "merge main in" commit alone doesn't count as work.
function branchHasWork(branch: string): boolean {
  const out = git(`diff --name-only main...${branch}`);
  return out !== null && out.length > 0;
}

// Predicate for base resolution: does a parent issue's branch exist locally with
// work not yet in `main`? True only when `sandcastle/issue-<id>` is a real ref
// AND its three-dot diff from main is non-empty (built this run, not yet merged).
// A parent that already landed in an earlier run has no local branch (or one with
// no unmerged work), so this returns false and the dependent issue bases on main.
function branchExistsWithWork(parentId: string): boolean {
  const branch = issueBranch(parentId);
  // `rev-parse --verify` exits non-zero (git() → null) when the ref is missing.
  if (git(`rev-parse --verify --quiet ${branch}`) === null) return false;
  return branchHasWork(branch);
}

// Whether `branch` still merges into main without conflict. merge-tree writes
// the merged tree and exits non-zero (git() → null) when the merge would
// conflict — a read-only check, no worktree or index mutation. A stranded
// branch that fails this is stale (main moved on while it sat in-review): it
// must be rebuilt from scratch, not injected to Phase 3 where it would only
// conflict again.
function mergesCleanIntoMain(branch: string): boolean {
  return git(`merge-tree --write-tree main ${branch}`) !== null;
}

// add/remove as separate calls so a no-op remove never blocks the add.
function relabel(id: string, add: string, remove: string[]): void {
  gh(`issue edit ${id} --add-label "${add}"`);
  for (const label of remove) gh(`issue edit ${id} --remove-label "${label}"`);
}

// ---------------------------------------------------------------------------
// Reconciliation sweep helpers
// ---------------------------------------------------------------------------

// Fetch all open issues (all labels) for the bucketed run summary.
function listAllOpenIssues(): OpenIssue[] {
  return parseOpenIssues(
    gh(`issue list --state open --limit 200 --json number,title,labels`)
  );
}

// Query GitHub for all PRs and build a map of issueNumber → PRs that close it.
// Uses closingIssuesReferences (the field GitHub populates when a PR body
// contains a closing keyword such as "Closes #N"). The gh calls are the IO; the
// fragile response parsing lives in github-parse.mts (tested there).
function getPrsReferencingIssues(): Map<number, PrRef[]> {
  const nameWithOwner =
    gh(`repo view --json nameWithOwner --jq .nameWithOwner`) ?? "";
  const [owner, repo] = nameWithOwner.split("/");
  if (!owner || !repo) return new Map();

  return parsePrsClosingIssues(
    gh(
      `api graphql -f 'query={ repository(owner: "${owner}", name: "${repo}") { pullRequests(first: 100, states: [OPEN, CLOSED, MERGED]) { nodes { number state closingIssuesReferences(first: 20) { nodes { number } } } } } }'`
    )
  );
}

// Each in-review issue's `blockedBy` edge ids, keyed by issue number (issue
// #50). The reconciliation sweep uses these to rebuild a recovered branch's
// parents (see `parentsFromBlockedBy`) instead of dropping the dependency graph.
// One bulk query for the whole in-review set — no per-issue fetch — mirroring
// the `blockedBy` pull the planner already does in plan-prompt.md.
const blockedByRowsSchema = z.array(
  z.object({ number: z.number(), blockedBy: z.array(z.number()) })
);

function getBlockedByForInReview(): Map<number, number[]> {
  const out = gh(
    `issue list --state open --label "in-review" --limit 100 --json number,blockedBy --jq '[.[] | {number, blockedBy: [.blockedBy.nodes[].number]}]'`
  );
  const map = new Map<number, number[]>();
  if (!out) return map;
  for (const row of blockedByRowsSchema.parse(JSON.parse(out))) {
    map.set(row.number, row.blockedBy);
  }
  return map;
}

// GitHub's native sub-issue edge (each open issue's `parent` field), as a
// childId → parentId map (issue #90). Folded into the PR-set graph via
// `mergeParentEdges` at Phase 3 so a spec and a sub-issue that supersedes it
// group into ONE PR instead of two — the durable backstop to the LLM planner,
// which is told to honor `parent` (plan-prompt.md) but can still miss it. String
// ids match `CompletedIssue.parents`; `mergeParentEdges` only reads edges for
// issues completed this run, and `prComponents` drops any parent not present, so
// fetching the whole open set is harmless.
const parentRowsSchema = z.array(
  z.object({ number: z.number(), parent: z.number().nullable() })
);

function getParentEdges(): Map<string, string> {
  // ponytail: --limit 100 matches every other issue fetch here; a repo with
  // >100 open issues could miss a completed issue's parent edge (it then falls
  // back to the planner-declared parents). Raise the limit if that ceiling bites.
  const out = gh(
    `issue list --state open --limit 100 --json number,parent --jq '[.[] | {number, parent: .parent.number}]'`
  );
  const map = new Map<string, string>();
  if (!out) return map;
  for (const row of parentRowsSchema.parse(JSON.parse(out))) {
    if (row.parent !== null) map.set(String(row.number), String(row.parent));
  }
  return map;
}

// ---------------------------------------------------------------------------
// Reconciliation sweep: run once at run start to restore the invariant
//   in-review ⟺ an open PR references the issue.
//
// For each in-review issue:
//   • open PR exists              → human-gated; leave untouched
//   • only closed/merged PR(s)   → human vetoed; relabel ready-for-human
//   • no PR at all (stranded)    →
//       branch exists with work   → inject into completedFromSweep for Phase 3
//       no branch / no work       → relabel ready-for-agent
//
// Returns the sets needed by the end-of-run bucketed summary.
// ---------------------------------------------------------------------------
function reconciliationSweep(): {
  sweepInjected: Set<string>;
  sweepRequeued: Set<string>;
  completedFromSweep: CompletedIssue[];
} {
  const inReview = listIssues("in-review");
  if (inReview.length === 0) {
    return {
      sweepInjected: new Set(),
      sweepRequeued: new Set(),
      completedFromSweep: [],
    };
  }

  console.log(
    `\n=== Reconciliation sweep: ${inReview.length} in-review issue(s) ===\n`
  );
  const prsForIssues = getPrsReferencingIssues();
  const blockedByForIssues = getBlockedByForInReview();

  const sweepInjected = new Set<string>();
  const sweepRequeued = new Set<string>();
  const completedFromSweep: CompletedIssue[] = [];

  for (const issue of inReview) {
    const id = String(issue.number);
    const prs = prsForIssues.get(issue.number) ?? [];
    const classification = classifyInReviewIssue(prs);

    const branch = issueBranch(id);
    const branchExists = branchExistsWithWork(id);
    const mergesClean = branchExists && mergesCleanIntoMain(branch);
    const action = decideInReviewAction(classification, {
      branchExists,
      mergesClean,
    });

    if (action === "leave") {
      console.log(`  #${id} — human-gated (open PR exists); leaving untouched`);
    } else if (action === "relabel-human") {
      console.log(
        `  #${id} — human-vetoed (closed/merged PR, no open PR) → ready-for-human`
      );
      relabel(id, "ready-for-human", ["in-review"]);
    } else if (action === "inject") {
      // Branch still applies to main — just never got a PR (e.g. a prior run
      // crashed before Phase 3). Inject it for a cheap PR, no rebuild.
      console.log(
        `  #${id} — stranded; branch ${branch} merges clean → injecting into this run for PR`
      );
      sweepInjected.add(id);
      completedFromSweep.push({
        id,
        title: issue.title,
        branch,
        // Rebuild the dependency graph from GitHub blockedBy edges (issue #50);
        // prComponents drops any parent not also completed this run, so a
        // stacked recovery collapses into one PR instead of one per tip.
        parents: parentsFromBlockedBy(blockedByForIssues.get(issue.number) ?? []),
      });
    } else {
      // requeue: no branch, no work, OR a stale branch that conflicts with main.
      // Requeue NOW (before the plan loop) so this run rebuilds it from scratch —
      // relabel ready-for-agent and delete any stale branch so Phase 2 recuts it
      // fresh from main (a lingering branch is only rebased onto base, keeping its
      // conflicting history).
      console.log(
        `  #${id} — stranded; no usable branch (missing or conflicts with main) → ready-for-agent for fresh rebuild`
      );
      git(`branch -D ${branch}`); // no-op (null) if the branch doesn't exist
      relabel(id, "ready-for-agent", ["in-review"]);
      sweepRequeued.add(id);
    }
  }

  return { sweepInjected, sweepRequeued, completedFromSweep };
}

// Ensure the lifecycle labels exist (idempotent — gh errors if present, swallowed).
gh(
  `label create in-review --color FBCA04 --description "Implemented + reviewed by sandcastle; PR pending human merge"`
);
gh(
  `label create needs-review --color D93F0B --description "Implemented but sandcastle review failed; re-review only"`
);

// The planner emits its plan as JSON inside <plan> tags; Output.object extracts
// and validates it against this schema. We use Zod here, but any Standard
// Schema validator works just as well — Valibot, ArkType, etc. See
// https://standardschema.dev.
const planSchema = z.object({
  issues: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      branch: z.string(),
      // The issue ids this issue builds on — its parents in the dependency
      // forest. Drawn from open blockers AND the completed-this-run list. The
      // planner biases toward declaring a parent when unsure: a missed parent
      // breaks the dependent's build, while a false parent only over-groups.
      // Base resolution (below) cuts each issue's branch from its parent's
      // branch (1 parent, present this run) or `main` (0 parents, or parent
      // already merged). Empty array for a root.
      parents: z.array(z.string()),
      // Topic key (issue #129): a short slug grouping issues that belong in the
      // same PR by feature/theme, even when no dependency links them. Issues
      // sharing a group are combined into one PR; dependency edges still force
      // same-PR regardless. The planner reuses an existing group from
      // COMPLETED_THIS_RUN when an issue fits one, so keys stay stable across
      // iterations.
      group: z.string(),
    })
  ),
});

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Maximum number of plan→execute cycles before stopping. This is only a backstop:
// the loop already breaks the moment a plan yields no buildable work
// (`work.length === 0`), so a run naturally drains the buildable backlog before
// hitting the cap. Set high so iterate-to-drain is the norm and the cap only
// guards against a pathological re-planning loop.
const MAX_ITERATIONS = 20;

// Resolve sandbox identity. No-op when bot env vars are unset.
// GitHub caps App installation tokens at ~1h, so a token minted once dies on any
// run that outlasts it (retries routinely push past the hour). We re-mint at the
// top of each iteration (below) instead; `identity` is reassigned there, and
// applyBotToken pushes each fresh token into process.env so the host gh()/git()
// calls stay authenticated too. This first mint covers Phase 0 + the sweep.
let identity = await sandboxIdentity();
applyBotToken(identity, process.env);

// Copy the host's virtualenv into the worktree before each sandbox starts.
// Avoids resolving+downloading every dependency from scratch; sandboxConfig's
// `uv sync` hook reconciles anything added since the copy.
const copyToWorktree = [".venv"];

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

// One run → one PR per PR set. We accumulate every completed issue across all
// iterations and, at the end, partition them into PR sets (dependency components,
// with same-topic components combined) and open one PR each.
//
// There is no integration tip anymore: the forest builds each issue on its real
// parent's branch (or main), so there is nothing to fold onto. `runId` survives
// only to name the throwaway PR head branches the host builds at Phase 3.
const runId = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);

// Branch refs and commits persist — only the checkout dirs go. Called at run
// start (crash-recovery net for a run that died before cleanup) and at run end
// (after Phase 3, once per-issue worktrees are dead). The onWorktreeReady
// rebase re-aligns any branch that is recut from its resolved base.
function gcWorktrees(): void {
  for (const path of parseSandcastleWorktrees(
    git(`worktree list --porcelain`) ?? ""
  )) {
    git(`worktree remove --force ${path}`);
  }
  git(`worktree prune`);
}

gcWorktrees();
// Branch the top-level runs (planner, PR consolidator) report against — used
// only to name their log files the way sandcastle would by default.
const headBranch = git("rev-parse --abbrev-ref HEAD") ?? "main";
// Every issue completed this run, with the parent edges the planner declared.
// Parent branches are immutable once done, so recording an issue here is pure
// bookkeeping — no git mutation. `parents` feeds back into the next planner
// iteration (so dependent issues can declare these as parents) and drives the
// Phase 3 head merge.
const allCompleted: CompletedIssue[] = [];

// Issues aborted this run because their multi-parent base could not be built:
// two declared parents conflict when merged (issue #64). Parent branches are
// static across a run's iterations, so the merge fails identically every time —
// re-attempting burns iterations for nothing. We block the issue for the rest of
// THIS run (no GitHub label: the block evaporates next run, and self-heals once a
// human merges the conflicting parents into main). Map value is the conflicting
// parent ids, so the run summary can name them. Authoritative hard gate; the
// planner is also told (BLOCKED_THIS_RUN) so it stops re-selecting them.
const blockedThisRun = new Map<string, string[]>();

// Phase 0: clear pending review comments on open sandcastle PRs before taking
// on new issue work. Once per run — humans don't comment mid-run, so a
// per-iteration sweep would only re-scan the same set. Set SANDCASTLE_SKIP_ADDRESS=1
// for an issues-only run.
if (process.env.SANDCASTLE_SKIP_ADDRESS !== "1") {
  console.log("\n=== Phase 0: Address open sandcastle PR comments ===\n");
  await addressOpenPRs();
}

// Pre-loop reconciliation sweep: restore in-review ⟺ open PR invariant before
// the plan loop runs. Stranded branches are injected into allCompleted so Phase 3
// opens their PRs; issues with no branch are relabeled ready-for-agent so the
// planner can re-build them.
const { sweepInjected, sweepRequeued, completedFromSweep } =
  reconciliationSweep();
allCompleted.push(...completedFromSweep);

// Track issue → PR number across all Phase 3 opens for the run summary.
const prAssignments = new Map<string, number>();

// Issue id → bounded failing-test tail for sets retired by the Phase-3
// consecutive gate-failure cap (#25). A retired set is relabeled ready-for-human,
// has its work branch PRESERVED (skipped in the post-Phase-3 reconciliation
// below), and is named — with its failing tests — in the run summary.
const retiredByGate = new Map<string, string>();

for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
  console.log(`\n=== Iteration ${iteration}/${MAX_ITERATIONS} ===\n`);

  // Re-mint before this iteration's sandboxes are cut: installation tokens
  // expire ~1h after minting, so a long run's later iterations would otherwise
  // bake a dead token into every sandbox (and the host gh() calls) and 401.
  // Minting is one JWT sign + one REST call — cheap enough to do every pass.
  identity = await sandboxIdentity();
  applyBotToken(identity, process.env);

  // -------------------------------------------------------------------------
  // Phase 1: Plan
  //
  // The planning agent (opus, for deeper reasoning) reads the open issue list,
  // builds a dependency graph, and selects the issues that can be worked in
  // parallel right now (i.e., no blocking dependencies on other open issues).
  //
  // It outputs a <plan> JSON block — Output.object parses and validates it.
  // -------------------------------------------------------------------------
  const plan = await sandcastle.run({
    ...sandboxConfig(identity),
    name: "planner",
    logging: logging("planner", headBranch),
    // One iteration is enough: the planner just needs to read and reason,
    // not write code. (Structured output requires maxIterations: 1.)
    maxIterations: 1,
    // Opus for planning: dependency analysis benefits from deeper reasoning.
    agent: sandcastle.claudeCode("claude-opus-4-8"),
    promptFile: "./.sandcastle/plan-prompt.md",
    // Issues already completed earlier in THIS run. Their branches exist locally
    // with work, so an issue depending only on these is unblocked — the planner
    // must build on top of them (declare them as `parents`), not treat them as
    // in-flight blockers. We surface each one's own parents AND its assigned group
    // so the planner keeps declaring consistent edges and REUSES existing group
    // keys (issue #129) instead of coining a new synonym that would split a topic
    // across PRs.
    promptArgs: {
      COMPLETED_THIS_RUN: allCompleted.length
        ? allCompleted
            .map((i) => {
              const parents = i.parents.length
                ? ` (builds on ${i.parents.map((p) => `#${p}`).join(", ")})`
                : "";
              const group = i.group ? ` [group: ${i.group}]` : "";
              return `- #${i.id} — ${i.title}${parents}${group}`;
            })
            .join("\n")
        : "(none yet — first iteration)",
      // Issues aborted this run by a deterministic multi-parent conflict (#64).
      // They cannot be built until a human merges their conflicting parents, so
      // the planner must NOT re-select them this run. Belt-and-suspenders: the
      // host also hard-drops them from `work` above.
      BLOCKED_THIS_RUN: blockedThisRun.size
        ? [...blockedThisRun]
            .map(
              ([id, parents]) =>
                `- #${id} — parents ${parents
                  .map((p) => `#${p}`)
                  .join(", ")} conflict; do not select`
            )
            .join("\n")
        : "(none)",
    },
    // Extract and validate the <plan> JSON into a typed object. Throws
    // StructuredOutputError if the tag is missing, the JSON is malformed, or
    // validation fails — which aborts the loop.
    output: sandcastle.Output.object({ tag: "plan", schema: planSchema }),
  });

  // Fresh, unblocked issues from the planner run the full implement→review
  // pipeline. Issues labelled needs-review (implemented earlier, review errored)
  // skip the implementer and re-run ONLY the reviewer on their existing branch.
  //
  // Drop anything this run already completed in an earlier iteration. The
  // planner sources its ready-for-agent list from GitHub's label SEARCH index,
  // which is eventually consistent: an issue relabeled in-review at the end of
  // iteration N can still surface as ready-for-agent when iteration N+1's
  // planner queries a second later, so it gets re-selected and needlessly
  // re-implemented (the implementer no-ops, but it still burns a sandbox + a
  // reviewer pass that makes throwaway commits). allCompleted is authoritative
  // local state with no index lag — filter against it.
  const handled = new Set(allCompleted.map((i) => i.id));
  const fresh = plan.output.issues
    // Also drop issues blocked this run by a multi-parent conflict (#64) — the
    // hard gate, in case the planner re-selects one despite BLOCKED_THIS_RUN.
    .filter((i) => !handled.has(i.id) && !blockedThisRun.has(i.id))
    .map((i) => ({
      ...i,
      mode: "full" as const,
    }));
  const needsReview = listIssues("needs-review").map((i) => ({
    id: String(i.number),
    title: i.title,
    branch: `sandcastle/issue-${i.number}`,
    mode: "review-only" as const,
  }));
  const work = [...fresh, ...needsReview];

  if (work.length === 0) {
    // No unblocked work and nothing awaiting re-review — done or all blocked.
    console.log("No unblocked or review-pending issues. Exiting.");
    break;
  }

  console.log(
    `Planning complete. ${fresh.length} to implement, ${needsReview.length} to re-review:`
  );
  for (const w of work) {
    console.log(`  [${w.mode}] ${w.id}: ${w.title} → ${w.branch}`);
  }

  // -------------------------------------------------------------------------
  // Phase 2: Execute + Review
  //
  // For each issue, create a sandbox via createSandbox() so the implementer
  // and reviewer share the same sandbox instance per branch. The implementer
  // runs first; if it produces commits, the reviewer runs in the same sandbox.
  //
  // Promise.allSettled means one failing pipeline doesn't cancel the others.
  // -------------------------------------------------------------------------

  const settled = await Promise.allSettled(
    work.map(async (issue) => {
      // Resolve this issue's base in the forest from its declared parents:
      //   0 parents          → main
      //   1 parent this run  → sandcastle/issue-<parent> (stack on the chain)
      //   1 parent merged    → main (its work already landed earlier)
      //   ≥2 parents (diamond) → a temp base branch merging all parents
      //                          (buildMultiParentBase), or null if that merge
      //                          conflicts — then skip the issue this iteration.
      // review-only issues have no plan entry, so default their parents to [].
      const parents = issue.mode === "full" ? issue.parents : [];
      const base = resolveBase({
        parents,
        branchExistsWithWork,
        onMultiParent: (ps) =>
          buildMultiParentBase(issue.id, ps, { git, branchExistsWithWork }),
      });
      if (base === null) {
        // Deterministic conflict: the parents conflict with each other, so this
        // fails identically every iteration. Block the issue for the rest of the
        // run (see blockedThisRun) instead of re-skipping to the iteration cap —
        // it needs a human to merge the parents upstream first (#64).
        blockedThisRun.set(issue.id, parents);
        console.error(
          `  ✗ ${issue.id} multi-parent base merge conflicted (${parents
            .map((p) => `#${p}`)
            .join(", ")}); blocked this run — merge parents upstream first`
        );
        return { issue, kind: "nothing" as const };
      }

      // A pre-existing branch (a review-only re-review, or a ready-for-agent
      // issue whose stale worktree lingers from an earlier run) was built
      // against an older base. Bring it up to its resolved base by REBASING onto
      // it (not merging) so the branch stays linear — a merge commit here would
      // make the issue un-revisable later, and would also entangle the diff the
      // reviewer sees. A fresh branch cut from the base rebases as a no-op; a
      // stale branch replays its commits onto the base. Best-effort: abort on
      // conflict and proceed; the retry cap escalates a branch that can't be
      // salvaged.
      const cfg = sandboxConfig(identity);
      const sandbox = await sandcastle.createSandbox({
        branch: issue.branch,
        // New branches are cut from the resolved base — the parent's branch (so
        // they contain just that chain's work) or main. (Ignored if the branch
        // already exists — the rebase hook above refreshes those.)
        baseBranch: base,
        ...cfg,
        hooks: {
          ...cfg.hooks,
          host: {
            onWorktreeReady: [
              {
                command: `git rebase ${base} || git rebase --abort`,
              },
            ],
          },
        },
        copyToWorktree,
      });

      try {
        // Implement (full mode only). review-only issues already have commits
        // on their branch from an earlier run.
        let implemented = false;
        if (issue.mode === "full") {
          const implement = await sandbox.run({
            name: "implementer",
            logging: logging("implementer", issue.branch),
            maxIterations: 100,
            agent: sandcastle.claudeCode("claude-sonnet-5"),
            promptFile: "./.sandcastle/implement-prompt.md",
            promptArgs: {
              TASK_ID: issue.id,
              ISSUE_TITLE: issue.title,
              BRANCH: issue.branch,
            },
          });
          implemented = implement.commits.length > 0;
        }

        // Decide whether to review by what's ON THE BRANCH, not by this run's
        // commit count. A resumed branch that's already complete yields zero
        // new commits but still has work to review; gating on this-run commits
        // there left the issue ready-for-agent and re-planned it every
        // iteration. Only a branch with no diff vs main is truly "nothing".
        if (!implemented && !branchHasWork(issue.branch)) {
          return { issue, kind: "nothing" as const };
        }

        // Review. A reviewer error (e.g. context blow-up) must NOT discard the
        // implementer's commits — catch it and flag the issue needs-review so a
        // later pass re-reviews the existing branch instead of re-implementing.
        // The originating issue text, so the reviewer can judge spec-conformance
        // (issue #130) independently — it sees ONLY the issue, the commits, and
        // the diff, never the implementer's reasoning.
        const issueSpec =
          gh(
            `issue view ${issue.id} --json title,body --jq '.title + "\n\n" + .body'`
          ) ?? "(issue text unavailable)";

        try {
          // Two read-only judges replace the single committing reviewer (#1):
          // a Spec judge and a Standards judge, each in its own isolated context
          // so neither sees the other's working notes. Both diff against this
          // issue's resolved base — its parent's branch or main. The base is
          // immutable for the issue's lifetime in the forest, so the judges see
          // only THIS issue's commits, not the parent chain it was stacked on.
          // Can't reuse the built-in TARGET_BRANCH arg — sandcastle reserves it
          // and pins it to the host branch (main), which would leak the parent
          // chain's commits into the diff. Neither judge writes the branch; the
          // implementer is the sole writer. Run them sequentially — both are
          // read-only, so order is irrelevant.
          const specReview = await sandbox.run({
            name: "spec-reviewer",
            logging: logging("spec-reviewer", issue.branch),
            maxIterations: 1,
            agent: sandcastle.claudeCode("claude-sonnet-5"),
            promptFile: "./.sandcastle/review-spec-prompt.md",
            promptArgs: {
              BRANCH: issue.branch,
              REVIEW_BASE: base,
              ISSUE_SPEC: `#${issue.id} ${issueSpec}`,
            },
          });
          const standardsReview = await sandbox.run({
            name: "standards-reviewer",
            logging: logging("standards-reviewer", issue.branch),
            maxIterations: 1,
            agent: sandcastle.claudeCode("claude-sonnet-5"),
            promptFile: "./.sandcastle/review-standards-prompt.md",
            promptArgs: {
              BRANCH: issue.branch,
              REVIEW_BASE: base,
            },
          });
          // Each judge emits a sentinel line (sandbox.run has no structured
          // output, #130). Fail-open per axis: only an explicit FAIL blocks.
          const specVerdict = parseSpecVerdict(specReview.stdout);
          const standardsVerdict = parseStandardsVerdict(standardsReview.stdout);
          const combined = combineVerdicts(specVerdict, standardsVerdict);
          if (!combined.pass) {
            // Post the failing judges' findings so the re-implement pass — the
            // sole writer — gets targeted context. Route through the existing
            // spec-fail path (shared REVIEW_RETRY_CAP; escalates to
            // ready-for-human at the cap).
            const sections: string[] = [];
            if (!specVerdict.pass)
              sections.push(`### Spec axis — FAIL\n\n${specReview.stdout.trim()}`);
            if (!standardsVerdict.pass)
              sections.push(
                `### Standards axis — FAIL\n\n${standardsReview.stdout.trim()}`
              );
            const body =
              `## Sandcastle review — changes requested\n\n` +
              `This branch was reviewed read-only on two axes; the axes below ` +
              `failed. Re-implement to address the findings (don't just silence ` +
              `the verdict line).\n\n` +
              sections.join("\n\n");
            commentIssues([issue.id], `review-findings-${issue.id}`, body);
            console.warn(
              `  ⚠ ${issue.id} failed review (${combined.failedAxes.join(
                ", "
              )})`
            );
            return { issue, kind: "spec-fail" as const };
          }
          return { issue, kind: "done" as const };
        } catch (e) {
          // A harness fault (the review prompt couldn't be assembled) is not a
          // bad branch — it fails identically for every issue, so swallowing it
          // to needs-review would burn retry caps and mislabel good work.
          // Rethrow so allSettled surfaces it and the run aborts (below).
          if (isHarnessError(e)) throw e;
          console.error(`  ⚠ ${issue.id} review failed, will re-review: ${e}`);
          return { issue, kind: "needs-review" as const };
        }
      } finally {
        await sandbox.close();
      }
    })
  );

  // Log any pipelines that threw outright (sandbox crash, network, etc.).
  let harnessFault: unknown = null;
  for (const [i, outcome] of settled.entries()) {
    if (outcome.status === "rejected") {
      console.error(
        `  ✗ ${work[i]!.id} (${work[i]!.branch}) failed: ${outcome.reason}`
      );
      if (isHarnessError(outcome.reason)) harnessFault ??= outcome.reason;
    }
  }

  // A harness fault means a prompt's preprocessor command failed — the harness
  // itself is broken and will fail identically for every issue. Abort the whole
  // run BEFORE the label-transition loop below, so no good branch gets mislabeled
  // and no retry cap is burned. A human fixes the prompt and re-runs; the issues
  // keep whatever label Phase 1 left them with.
  if (harnessFault) {
    throw new Error(
      `Aborting run: review harness fault — a prompt's preprocessor command ` +
        `failed, which breaks review for every issue. Fix the prompt and re-run. ` +
        `Cause: ${harnessFault}`
    );
  }

  // Transition each issue's label the moment its outcome is known, so the NEXT
  // iteration's planner (and any future run) sees the right state. Which label
  // each outcome lands on is planOutcomeTransition's call (#102, ADR-0002); this
  // loop only applies the plan it returns. A rejection carries no value, so its
  // issue comes from `work` by index.
  let attempts = readAttempts();
  const completedIssues: CompletedIssue[] = [];
  for (const [i, outcome] of settled.entries()) {
    const issue = outcome.status === "fulfilled" ? outcome.value.issue : work[i]!;
    const kind =
      outcome.status === "fulfilled" ? outcome.value.kind : ("nothing" as const);
    const plan = planOutcomeTransition({ kind, issue, attempts });
    attempts = plan.attempts;
    if (plan.addLabel) relabel(issue.id, plan.addLabel, plan.removeLabels);
    if (plan.note) console.warn(`  ${plan.note}`);
    // A completed issue's branch IS its place in the forest; it was built on its
    // real parent, so there is nothing to fold and the parent branch is
    // immutable from here. Recording the edge is all Phase 3 needs.
    if (plan.completed) completedIssues.push(plan.completed);
  }
  writeAttempts(attempts);

  console.log(
    `\nExecution complete. ${completedIssues.length} issue(s) reviewed and ready for PR:`
  );
  for (const issue of completedIssues) {
    console.log(`  ${issue.branch}`);
  }

  if (completedIssues.length === 0) {
    console.log("Nothing newly completed this iteration.");
    continue;
  }

  // -------------------------------------------------------------------------
  // Accumulate, do NOT open PRs yet. Phase 3 opens them after the outer loop
  // ends — one per PR set (dependency component, with same-topic components
  // combined).
  // -------------------------------------------------------------------------
  allCompleted.push(...completedIssues);
  console.log(
    `Accumulated ${completedIssues.length} issue(s) this iteration; ${allCompleted.length} total so far.`
  );
}

// ---------------------------------------------------------------------------
// Phase 3: One PR per PR set
//
// The run built a forest; now open ONE pull request per PR set — a connected
// component of `{parent edges} ∪ {same-group edges}` (prComponents). Dependency
// links and shared topic both pull issues into the same set, but a dependency
// edge always wins, so a chain is never split. Each set is independent off `main`
// (no shared commits), so its PR merges in any order with no rebase surgery.
//
// Per set the host assembles a throwaway head off `main`
// (`sandcastle/pr-<runId>-<n>`) by merging in the set's LEAF TIPS — issues no
// fellow member builds on. A child branch already contains its ancestors, so
// merging the leaves pulls in each chain exactly once (a fork or a topic-merged
// set has several leaves; a diamond collapses to one). The host force-pushes each
// head and an agent opens ONE PR from it into main (prose only — the agent runs
// no git).
// ---------------------------------------------------------------------------
// Fold GitHub sub-issue (`parent`) edges into the graph before grouping (issue
// #90), so a spec and a child that supersedes it land in one PR set even when the
// planner declared no edge between them. One fetch covers every completed issue —
// fresh-plan and sweep-injected alike — so this is the single deterministic
// chokepoint the LLM planner can't slip past.
const components = prComponents(mergeParentEdges(allCompleted, getParentEdges()));
if (components.length === 0) {
  console.log("\nNo completed issues across the run. No PR to open.");
} else {
  console.log(
    `\nOpening ${components.length} PR(s), one per PR set, for ` +
      `${allCompleted.length} completed issue(s).`
  );
  for (const [n, component] of components.entries()) {
    const prBranch = `sandcastle/pr-${runId}-${n + 1}`;
    const { issues, leaves } = component;
    console.log(
      `\nComponent ${n + 1}/${components.length}: ${issues.length} issue(s), ` +
        `${leaves.length} leaf tip(s) → ${prBranch}`
    );

    // Build the head in a scratch worktree so the host's checkout is untouched.
    // Start at main, then merge each leaf tip in. Conflicts between independent
    // chains are not expected (the planner co-selects non-overlapping issues); a
    // conflicting merge aborts and that leaf is logged and skipped rather than
    // corrupting the head.
    git(`branch -f ${prBranch} main`);
    const wt = `.sandcastle/pr-head-${runId}-${n + 1}`;
    git(`worktree remove --force ${wt}`); // clear any stale scratch worktree
    git(`worktree add --force ${wt} ${prBranch}`);
    for (const leaf of leaves) {
      const ok = git(
        `-C ${wt} merge --no-edit -m "Merge ${leaf.branch} into ${prBranch}" ${leaf.branch}`
      );
      if (ok === null) {
        git(`-C ${wt} merge --abort`);
        console.error(
          `  ✗ ${leaf.id} (${leaf.branch}) conflicted merging into ${prBranch}; excluded from the PR head`
        );
        // No requeue here: any issue left without a PR — a conflicting leaf, OR a
        // non-leaf that a spurious parent edge made unmergeable — is repaired
        // uniformly by the post-Phase-3 strand reconciliation below, which also
        // deletes the stale branch so the rebuild cuts fresh. (Superseded #149's
        // narrow sweepInjected-leaf-only check, which missed both those cases.)
      }
    }
    git(`worktree remove --force ${wt}`);

    // If every leaf merge conflicted and aborted, the head is still bare `main`
    // with nothing ahead — opening a PR from it would be an empty no-op. Skip the
    // whole component in that case rather than pushing main-onto-main and asking
    // the agent to open an empty PR.
    const ahead = git(`rev-list --count main..${prBranch}`);
    if (ahead === null || ahead === "0") {
      console.error(
        `  ✗ Component ${n + 1}: no commits landed on ${prBranch} ` +
          `(all ${leaves.length} leaf merge(s) conflicted); skipping its PR.`
      );
      continue;
    }

    // -----------------------------------------------------------------------
    // Full-suite gate (#22): before opening the PR, run the whole `just check`
    // (lint + typecheck + tests) on the assembled head IN A SANDBOX — the same
    // toolchain the target's CI runs, never the bare host worktree — so a red set
    // never reaches a human as an open PR. A green verdict opens as today; any
    // non-pass withholds the PR and requeues the whole set: the failing tail is
    // commented on every issue, then the set flows into the post-Phase-3
    // reconciliation below (which relabels ready-for-agent + deletes the stale
    // branch) so the next iteration rebuilds it informed by the comment.
    //
    // The gate agent runs `just check && echo <sentinel>` and reports its raw
    // stdout; parseCheckVerdict reads the sentinel and fails CLOSED — a crashed or
    // garbled check is test-fail, and only a THROWN sandbox/harness fault (caught
    // below, passed as `error`) classifies as harness-error. Both non-pass verdicts
    // requeue; harness-error is retried next iteration without a real code failure.
    // -----------------------------------------------------------------------
    const gateIds = issues.map((i) => i.id);
    let checkStdout = "";
    let checkError: unknown;
    try {
      const gateCfg = sandboxConfig(identity);
      const gate = await sandcastle.createSandbox({
        branch: prBranch, // already built + local; checked out, not re-cut
        ...gateCfg,
        copyToWorktree, // seed .venv so `just check` reuses deps, no re-resolve
      });
      try {
        const check = await gate.run({
          name: `check-gate-${n + 1}`,
          logging: logging(`check-gate-${n + 1}`, prBranch),
          maxIterations: 1,
          agent: sandcastle.claudeCode("claude-sonnet-5"),
          promptFile: "./.sandcastle/check-prompt.md",
          promptArgs: { MERGE_HEAD: prBranch },
        });
        checkStdout = check.stdout;
      } finally {
        await gate.close();
      }
    } catch (e) {
      // The harness-error channel parseCheckVerdict reads via `error` — a thrown
      // FiberFailure (prompt assembly, sandbox launch), never scanned from stdout.
      // Requeue rather than abort: a bad head is not a broken run.
      checkError = e;
    }

    const verdict = parseCheckVerdict(checkStdout, checkError);

    // Consecutive gate-failure cap (#25): count one failure per issue under key
    // gate-<id>. A real "test-fail" increments and may escalate at the cap; a
    // "harness-error" is an infra fault and is NEVER counted (it can't retire a
    // good set); a "pass" clears the counter so the cap is CONSECUTIVE failures.
    // The set fails and passes the gate in lockstep, so all its gate-<id>
    // counters move together and escalate on the same iteration.
    let escalated = false;
    {
      let gateAttempts = readAttempts();
      if (verdict.status === "pass") {
        for (const id of gateIds) delete gateAttempts[`gate-${id}`];
      } else if (verdict.status === "test-fail") {
        for (const id of gateIds) {
          const r = recordAttempt(gateAttempts, `gate-${id}`);
          gateAttempts = r.attempts;
          // OR-reduce, not last-wins: the set escalates if ANY member hit the
          // cap. In lockstep every gate-<id> escalates together, but recordAttempt
          // deletes a key when it escalates, so were the counters ever out of step
          // a last-wins read could miss an escalation and loop the set forever.
          escalated ||= r.escalate;
        }
      }
      writeAttempts(gateAttempts);
    }

    const plan = planGateOutcome(verdict, gateIds, escalated);

    if (plan.action === "retire") {
      // The set has failed the full suite REVIEW_RETRY_CAP times running.
      // Requeuing again would loop forever, so park it on a human: relabel
      // ready-for-human, comment the failing tail, and — when the plan says so —
      // PRESERVE the work branch. Recording the id in retiredByGate is what
      // preserves it: the post-Phase-3 reconciliation below skips those ids, so
      // the human inherits the actual failing tree instead of a deleted branch.
      const body =
        `## Sandcastle full-suite gate — retired to a human\n\n` +
        `\`just check\` on this set's merged head (\`${prBranch}\`) failed the ` +
        `full suite ${REVIEW_RETRY_CAP} times running, so the set is parked as ` +
        `**ready-for-human** rather than requeued again. Its work branch is ` +
        `preserved for you to inspect. Address the failure below.\n\n` +
        "```\n" +
        `${verdict.tail || "(no output captured)"}\n` +
        "```\n";
      commentIssues(plan.commentIssueIds, `check-gate-${runId}-${n + 1}`, body);
      for (const id of plan.commentIssueIds) {
        relabel(id, "ready-for-human", [
          "ready-for-agent",
          "needs-review",
          "in-review",
        ]);
        if (plan.preserveBranch)
          retiredByGate.set(id, plan.summaryNote ?? verdict.tail);
      }
      console.error(
        `  ✗ Component ${n + 1}: full-suite gate failed ${REVIEW_RETRY_CAP}x; ` +
          `set retired → ready-for-human (branch ${prBranch} preserved).`
      );
      continue; // skip push + PR open; reconciliation must not touch these
    }

    if (plan.action === "requeue") {
      const body =
        `## Sandcastle full-suite gate — PR withheld\n\n` +
        `\`just check\` on this set's merged head (\`${prBranch}\`) came back ` +
        `**${verdict.status}**, so no PR was opened. The set is requeued for a ` +
        `fresh rebuild — address the failure below, don't just silence it.\n\n` +
        "```\n" +
        `${verdict.tail || "(no output captured)"}\n` +
        "```\n";
      commentIssues(plan.commentIssueIds, `check-gate-${runId}-${n + 1}`, body);
      console.error(
        `  ✗ Component ${n + 1}: full-suite gate ${verdict.status}; PR withheld, ` +
          `${plan.commentIssueIds.length} issue(s) commented → requeued.`
      );
      continue; // skip push + PR open; post-Phase-3 reconciliation requeues them
    }

    // Which of this set's issues actually reached the head (#115) — see
    // `landedIssues` for why ancestry rather than a set of failed leaf ids. The two
    // consumers that speak for the PR read THIS list, never `issues`: the PR body
    // below and `prAssignments` once the PR is open. An excluded issue is therefore
    // neither named in the PR nor credited to it, which leaves the post-Phase-3
    // reconciliation — it skips any issue already assigned — free to re-queue it.
    // The gate paths above stay set-wide on purpose: no PR exists for them to lie
    // about. Computed here, after the gate, so a withheld PR spends no subprocesses.
    // `git` returns "" on success and null on failure, so compare against null —
    // `--is-ancestor` reports its verdict through the exit code and prints nothing.
    const landed = landedIssues(
      issues,
      (branch) => git(`merge-base --is-ancestor ${branch} ${prBranch}`) !== null
    );

    // Push the assembled head host-side so the agent only has to open the PR.
    git(`push -u --force-with-lease origin ${prBranch}`);
    await sandcastle.run({
      ...sandboxConfig(identity),
      name: `pr-consolidator-${n + 1}`,
      logging: logging(`pr-consolidator-${n + 1}`, headBranch),
      maxIterations: 1,
      agent: sandcastle.claudeCode("claude-sonnet-5"),
      promptFile: "./.sandcastle/pr-prompt.md",
      promptArgs: {
        MERGE_HEAD: prBranch,
        // One markdown line per issue whose commits are IN this head: id, title,
        // branch. Excluded issues are omitted — the PR must not claim work it
        // does not carry (#115).
        ISSUES: landed
          .map((i) => `- #${i.id} — ${i.title} (branch \`${i.branch}\`)`)
          .join("\n"),
      },
    });

    // Capture the PR number so the end-of-run summary can show "→ PR #N".
    const prNumRaw = gh(`pr view ${prBranch} --json number --jq .number`);
    const prNum = prNumRaw ? parseInt(prNumRaw, 10) : 0;
    if (prNum > 0) {
      for (const issue of landed) prAssignments.set(issue.id, prNum);
    }
  }
  console.log(`\n${components.length} PR(s) opened.`);
}

// ---------------------------------------------------------------------------
// Post-Phase-3 strand reconciliation: make "end a run in-review with no PR"
// structurally impossible.
//
// Every completed issue should now carry a PR (its component opened one). Any
// that does NOT — a leaf whose merge conflicted, or a non-leaf an unrelated
// parent edge pulled in but never merged — would otherwise be left in-review
// with a stale branch: a strand that loops forever (next run's sweep re-injects
// the same branch, it re-conflicts, re-skips).
//
// Repair it outcome-based, blind to leaf/group/injection nuance: relabel
// ready-for-agent, and DELETE the stale issue branch. Deletion is required, not
// cosmetic — Phase 2 only cuts a fresh branch from main when one does not exist;
// a lingering branch is merely rebased onto base and keeps its conflicting
// history. Move it sweepInjected → sweepRequeued so the summary reports it
// re-queued, never "PR opened".
for (const issue of allCompleted) {
  if (prAssignments.has(issue.id)) continue;
  // Retired by the gate cap (#25): already relabeled ready-for-human, and its
  // branch is deliberately preserved for the human — do NOT requeue or delete it.
  if (retiredByGate.has(issue.id)) continue;
  relabel(issue.id, "ready-for-agent", ["in-review", "needs-review"]);
  git(`branch -D ${issue.branch}`);
  sweepInjected.delete(issue.id);
  sweepRequeued.add(issue.id);
  console.error(
    `  ✗ #${issue.id} (${issue.branch}) completed but no PR opened (stranded); ` +
      `stale branch deleted → ready-for-agent for a fresh rebuild`
  );
}

// End-of-run worktree GC: remove any issue checkout dirs that Phase 3 left
// behind. PRs are open; the worktrees are dead.
gcWorktrees();

// ---------------------------------------------------------------------------
// End-of-run bucketed summary: account for every open issue in exactly one
// bucket so nothing is silently hidden behind "no work to do".
// ---------------------------------------------------------------------------
{
  const allOpenIssues = listAllOpenIssues();
  const bucketed = bucketIssues({
    openIssues: allOpenIssues,
    builtThisRun: new Set(allCompleted.map((i) => i.id)),
    sweepInjected,
    sweepRequeued,
    prAssignments,
    blockedByParentConflict: blockedThisRun,
    retiredByGate,
  });
  const summary = buildRunSummary(bucketed);
  console.log(summary);
  // Persist the summary — per-run filename so it survives the next run (the
  // per-agent logs overwrite). This is the run's ground-truth outcome and is
  // otherwise lost when the terminal scrolls.
  // ponytail: summary only; tee the whole orchestrator stdout if the sweep
  // trace is also needed for debugging.
  writeFileSync(`.sandcastle/logs/run-${runId}.log`, summary);
}

console.log("\nAll done.");
