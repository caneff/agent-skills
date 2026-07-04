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

export function parseSpecVerdict(stdout: string): SpecVerdict {
  const fail = stdout.match(/^SANDCASTLE_SPEC:\s*FAIL\b.*$/m);
  if (fail) return { pass: false, reason: fail[0].trim() };
  return { pass: true, reason: "" };
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
