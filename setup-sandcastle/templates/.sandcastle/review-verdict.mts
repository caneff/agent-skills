// Parse the reviewer's spec-conformance verdict from its stdout.
//
// sandbox.run has no structured output, so the reviewer emits a sentinel line —
// `SANDCASTLE_SPEC: PASS` or `SANDCASTLE_SPEC: FAIL — <reason>`. We gate on an
// EXPLICIT failure only: a FAIL line sends the issue back to be re-implemented;
// anything else (PASS, or no verdict at all) is treated as a pass. Fail-open on a
// missing verdict is deliberate — a reviewer that forgets the sentinel should not
// trigger a spurious re-implement; only an affirmative FAIL blocks acceptance.
//
// Pure function, unit-tested. The orchestrator passes review.stdout.
//
// ReviewAxis and the ReviewedOutcome union live in issue-lifecycle.mts — the
// lifecycle vocabulary's one home — and are imported back here.

import type { ReviewAxis, ReviewedOutcome } from "./issue-lifecycle.mts";
export type { ReviewAxis } from "./issue-lifecycle.mts";

export interface SpecVerdict {
  pass: boolean;
  // The matched FAIL line (with its reason) when pass is false; empty otherwise.
  reason: string;
}

// A single judge's verdict — both axes share this shape.
export type AxisVerdict = SpecVerdict;

// Both judges gate the same way, differing only in their sentinel word: only an
// explicit `SANDCASTLE_<AXIS>: FAIL` line blocks; a PASS or a missing sentinel
// passes (fail-open). The axis name is upper-cased into the contract string —
// host-coupled, see CODING_STANDARDS; don't reword the SANDCASTLE_… prefix.
export function parseAxisVerdict(stdout: string, axis: ReviewAxis): AxisVerdict {
  const sentinel = axis === "spec" ? "SPEC" : "STANDARDS";
  const fail = stdout.match(new RegExp(`^SANDCASTLE_${sentinel}:\\s*FAIL\\b.*$`, "m"));
  if (fail) return { pass: false, reason: fail[0].trim() };
  return { pass: true, reason: "" };
}

export const parseSpecVerdict = (stdout: string): AxisVerdict =>
  parseAxisVerdict(stdout, "spec");
export const parseStandardsVerdict = (stdout: string): AxisVerdict =>
  parseAxisVerdict(stdout, "standards");

export interface CombinedVerdict {
  // Overall gate: passes only when both axes pass.
  pass: boolean;
  // Which axes failed, in [spec, standards] order; empty when pass.
  failedAxes: ReviewAxis[];
  // The captured FAIL line for each failing axis, keyed by axis.
  reasons: Partial<Record<ReviewAxis, string>>;
}

// Fold the two isolated judges' verdicts into one gate. `pass` and `failedAxes`
// drive routing and the findings comment the orchestrator posts; `reasons`
// carries each failing axis's one-line FAIL summary for any caller that wants it
// (the orchestrator posts the judges' fuller stdout instead).
export function combineVerdicts(
  spec: AxisVerdict,
  standards: AxisVerdict
): CombinedVerdict {
  const failedAxes: ReviewAxis[] = [];
  const reasons: Partial<Record<ReviewAxis, string>> = {};
  if (!spec.pass) {
    failedAxes.push("spec");
    reasons.spec = spec.reason;
  }
  if (!standards.pass) {
    failedAxes.push("standards");
    reasons.standards = standards.reason;
  }
  return { pass: failedAxes.length === 0, failedAxes, reasons };
}

// Fold the two judges' verdicts into that outcome (ReviewedOutcome — see
// issue-lifecycle.mts). Absorbs combineVerdicts and
// the per-axis detail assembly that used to sit inline in main's Phase-2 closure:
// `done` when both pass, else `review-fail` naming the failed axes and keeping
// only the failed axes' detail (a passing axis's detail is dropped). The caller
// passes the fuller reviewer stdout per axis; the short FAIL lines stay inside
// combineVerdicts for anyone who wants them.
export function classifyReviewedOutcome(
  spec: AxisVerdict,
  standards: AxisVerdict,
  detail: Partial<Record<ReviewAxis, string>>
): ReviewedOutcome {
  const combined = combineVerdicts(spec, standards);
  if (combined.pass) return { kind: "done" };
  const reasons: Partial<Record<ReviewAxis, string>> = {};
  for (const axis of combined.failedAxes) {
    if (detail[axis] !== undefined) reasons[axis] = detail[axis];
  }
  return { kind: "review-fail", failedAxes: combined.failedAxes, reasons };
}

// Distinguish a broken-harness fault from a genuine review failure.
//
// A reviewer can fail two ways. Either the review RAN and the branch couldn't
// be salvaged (context blow-up, agent gave up) — that's per-issue, retry it.
// Or the review never started because the prompt itself couldn't be assembled:
// a `!`-command in the prompt template exited nonzero, so the preprocessor
// raised a PromptError. That is deterministic — it fails identically for every
// issue this run — so retrying only burns retry caps and mislabels good
// branches as bad code. The orchestrator aborts the whole run on these instead.
//
// Matches on the error's string form because the sandcastle runtime wraps it in
// an Effect FiberFailure (`(FiberFailure) PromptError: ...`); the PromptError
// class is not exported to import and instanceof-check directly.
export function isHarnessError(e: unknown): boolean {
  return /PromptError/.test(String(e));
}

