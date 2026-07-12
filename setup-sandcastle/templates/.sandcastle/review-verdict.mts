// Parse the reviewer's spec-conformance verdict from its stdout (issue #130).
//
// sandbox.run has no structured output, so the reviewer emits a sentinel line —
// `SANDCASTLE_SPEC: PASS` or `SANDCASTLE_SPEC: FAIL — <reason>`. We gate on an
// EXPLICIT failure only: a FAIL line sends the issue back to be re-implemented;
// anything else (PASS, or no verdict at all) is treated as a pass. Fail-open on a
// missing verdict is deliberate — a reviewer that forgets the sentinel should not
// trigger a spurious re-implement; only an affirmative FAIL blocks acceptance.
//
// Pure function, unit-tested. The orchestrator passes review.stdout.

export interface SpecVerdict {
  pass: boolean;
  // The matched FAIL line (with its reason) when pass is false; empty otherwise.
  reason: string;
}

// A single judge's verdict — both axes share this shape.
export type AxisVerdict = SpecVerdict;

export function parseSpecVerdict(stdout: string): AxisVerdict {
  const fail = stdout.match(/^SANDCASTLE_SPEC:\s*FAIL\b.*$/m);
  if (fail) return { pass: false, reason: fail[0].trim() };
  return { pass: true, reason: "" };
}

// The standards judge is gated identically to spec, on its own sentinel line
// (`SANDCASTLE_STANDARDS: PASS` / `... FAIL — <reason>`). Same fail-open rule:
// only an explicit FAIL blocks; a PASS or a missing sentinel passes.
export function parseStandardsVerdict(stdout: string): AxisVerdict {
  const fail = stdout.match(/^SANDCASTLE_STANDARDS:\s*FAIL\b.*$/m);
  if (fail) return { pass: false, reason: fail[0].trim() };
  return { pass: true, reason: "" };
}

export type ReviewAxis = "spec" | "standards";

export interface CombinedVerdict {
  // Overall gate: passes only when both axes pass.
  pass: boolean;
  // Which axes failed, in [spec, standards] order; empty when pass.
  failedAxes: ReviewAxis[];
  // The captured FAIL line for each failing axis, keyed by axis.
  reasons: Partial<Record<ReviewAxis, string>>;
}

// Fold the two isolated judges' verdicts into one gate. The re-implement pass
// reads failedAxes + reasons as targeted context for the fixes it must apply.
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
