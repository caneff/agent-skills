import { test, expect, describe } from "vitest";
import { parseSpecVerdict, isHarnessError } from "../review-verdict.mts";

// The reviewer emits a sentinel line because sandbox.run has no structured
// output (issue #130). Gate on an EXPLICIT FAIL only; everything else passes.
describe("parseSpecVerdict", () => {
  test("explicit PASS → pass", () => {
    expect(parseSpecVerdict("work done\nSANDCASTLE_SPEC: PASS\n")).toEqual({
      pass: true,
      reason: "",
    });
  });

  test("explicit FAIL → not pass, captures the reason line", () => {
    const v = parseSpecVerdict(
      "notes...\nSANDCASTLE_SPEC: FAIL — AC2 (dark-mode toggle) not implemented\n<promise>COMPLETE</promise>"
    );
    expect(v.pass).toBe(false);
    expect(v.reason).toContain("AC2 (dark-mode toggle) not implemented");
  });

  test("FAIL with no reason still fails", () => {
    expect(parseSpecVerdict("SANDCASTLE_SPEC: FAIL").pass).toBe(false);
  });

  test("no verdict at all → pass (fail-open on a missing sentinel)", () => {
    expect(parseSpecVerdict("reviewer said nothing useful").pass).toBe(true);
  });

  test("a FAIL buried among other output is still detected", () => {
    const out = [
      "refactored foo",
      "SANDCASTLE_SPEC: FAIL — missing error handling",
      "trailing chatter",
    ].join("\n");
    expect(parseSpecVerdict(out).pass).toBe(false);
  });

  test("the word FAIL elsewhere (not the sentinel) does not trip the gate", () => {
    expect(parseSpecVerdict("the test suite did not FAIL\n").pass).toBe(true);
  });
});

// A broken prompt (a `!`-command exits nonzero) surfaces as a PromptError wrapped
// in an Effect FiberFailure. The orchestrator must abort the run on these, not
// retry per-issue — they fail identically for every issue.
describe("isHarnessError", () => {
  test("a wrapped PromptError is a harness fault", () => {
    const e =
      "(FiberFailure) PromptError: Command `git diff ... && cat X` exited with code 1: ";
    expect(isHarnessError(e)).toBe(true);
  });

  test("an Error object carrying PromptError is detected via its string form", () => {
    expect(isHarnessError(new Error("PromptError: bad command"))).toBe(true);
  });

  test("an ordinary review failure (context blow-up) is NOT a harness fault", () => {
    expect(isHarnessError(new Error("context window exceeded"))).toBe(false);
  });

  test("null / undefined are not harness faults", () => {
    expect(isHarnessError(null)).toBe(false);
    expect(isHarnessError(undefined)).toBe(false);
  });
});
