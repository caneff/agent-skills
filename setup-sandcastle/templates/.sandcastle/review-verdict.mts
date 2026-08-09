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

// The full-suite gate's verdict (issue #22). Unlike the spec/standards judges —
// an agent OPINION that fails open on a missing sentinel — this is a safety gate
// over the repo's check gate (lint + typecheck + the whole test suite) and fails
// CLOSED:
//   - "pass"          the suite is green.
//   - "test-fail"     the suite failed, OR the output was missing/unparseable —
//                     a crashed check is not a green suite. Carries a bounded tail.
//   - "harness-error" a sandbox/harness fault, not the code's fault (reuses the
//                     isHarnessError notion) — the caller retries without counting
//                     it against the failure cap.
export type CheckStatus = "pass" | "test-fail" | "harness-error";

export interface CheckVerdict {
  status: CheckStatus;
  // Bounded failure context: failing test names + last N lines for "test-fail",
  // a bounded form of the fault for "harness-error"; empty on "pass".
  tail: string;
}

// The gate wrapper echoes this sentinel only when the repo's check command exits
// zero (`… && echo SANDCASTLE_CHECK: PASS`, rendered into check-prompt.md). No
// sentinel → not green → fail closed. Host-coupled contract string (see
// CODING_STANDARDS) — don't reword.
const CHECK_PASS = /^SANDCASTLE_CHECK:\s*PASS\s*$/m;

// Bound the forwarded failure context so a huge suite log never floods the issue
// or the requeued agent's context (issue #22). Two capped slices: the failing
// *names* the next attempt needs (vitest `FAIL …`, tsc `error TSxxxx`), followed
// by the raw last-N lines that carry the actual error. Both halves are bounded,
// so the total is bounded no matter how large the log is; names not already in
// the tail are kept, so the two halves don't duplicate.
const MAX_FAIL_LINES = 20;
const MAX_TAIL_LINES = 40;
const FAIL_LINE = /(^|\s)(FAIL|×|✗|✕|✖)(\s|$)|error TS\d+/;

function boundedTail(output: string): string {
  const lines = (output ?? "").split("\n");
  const lastN = lines.slice(-MAX_TAIL_LINES);
  const tailSet = new Set(lastN);
  const failNames = lines
    .filter((l) => FAIL_LINE.test(l) && !tailSet.has(l))
    .slice(0, MAX_FAIL_LINES);
  return [...failNames, ...lastN].join("\n").trim();
}

// `output` is the check's stdout; `error` is whatever the gate's sandbox.run
// THREW (undefined when it returned normally). The harness signal comes only
// from `error` — the same thrown-FiberFailure channel isHarnessError was built
// to read — never from scanning stdout, so a genuine test failure whose log
// merely mentions "PromptError" isn't misread as infrastructure flakiness.
export function parseCheckVerdict(
  output: string,
  error?: unknown
): CheckVerdict {
  // A thrown harness/sandbox fault: the check never really ran, so it's not the
  // code's fault. Classified first, before the pass/fail split, so the caller
  // can retry without counting it against the failure cap.
  if (error !== undefined && isHarnessError(error))
    return { status: "harness-error", tail: boundedTail(String(error)) };
  // A non-harness throw (or no throw) with no PASS sentinel fails CLOSED.
  if (CHECK_PASS.test(output)) return { status: "pass", tail: "" };
  return { status: "test-fail", tail: boundedTail(output || String(error ?? "")) };
}
