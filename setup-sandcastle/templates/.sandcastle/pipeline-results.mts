// Pure decisions over the Promise.allSettled array main's Phase 2 produces,
// lifted out of the phase flow so they test without standing up a live sandbox.
// main keeps the loop and all the git/gh IO; it just calls these.
import { isHarnessError } from "./review-verdict.mts";
// IssueOutcome lives in issue-lifecycle.mts — the lifecycle vocabulary's one
// home — imported here only for this module's own signatures below.
import type { IssueOutcome } from "./issue-lifecycle.mts";

// The run-aborting decision. A rejected PromptError means a prompt's preprocessor
// failed — it breaks review identically for every issue, so retrying per-issue
// only burns work and mislabels good branches. Return the first such reason (the
// caller aborts the whole run); a rejected ordinary error is per-issue and is
// left for normalizeSettled to turn into `nothing`.
export function firstHarnessFault(
  settled: PromiseSettledResult<unknown>[]
): unknown | null {
  for (const outcome of settled) {
    if (outcome.status === "rejected" && isHarnessError(outcome.reason)) {
      return outcome.reason;
    }
  }
  return null;
}

// Project the settled array to one typed list. A fulfilled pipeline passes its
// outcome through; a rejected one (sandbox crash, network) has no value, so its
// issue is recovered by index from `work` and it becomes `nothing`. Index
// alignment between `settled` and `work` is the contract Promise.allSettled keeps.
export function normalizeSettled<I>(
  settled: PromiseSettledResult<IssueOutcome<I>>[],
  work: I[]
): IssueOutcome<I>[] {
  return settled.map((outcome, i) =>
    outcome.status === "fulfilled"
      ? outcome.value
      : { issue: work[i]!, kind: "nothing" }
  );
}
