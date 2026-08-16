import { test, expect, describe } from "vitest";
import {
  parseSpecVerdict,
  parseStandardsVerdict,
  combineVerdicts,
  classifyReviewedOutcome,
  classifyRetryOutcome,
  isHarnessError,
} from "../review-verdict.mts";

// The reviewer emits a sentinel line because sandbox.run has no structured
// output. Gate on an EXPLICIT FAIL only; everything else passes.
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

// The standards judge emits its own sentinel line, gated identically to spec:
// only an explicit `SANDCASTLE_STANDARDS: FAIL` blocks; PASS or a missing
// sentinel is fail-open.
describe("parseStandardsVerdict", () => {
  test("explicit PASS → pass", () => {
    expect(
      parseStandardsVerdict("checked standards\nSANDCASTLE_STANDARDS: PASS\n")
    ).toEqual({ pass: true, reason: "" });
  });

  test("explicit FAIL → not pass, captures the reason line", () => {
    const v = parseStandardsVerdict(
      "notes...\nSANDCASTLE_STANDARDS: FAIL — no error handling on the DB call\n"
    );
    expect(v.pass).toBe(false);
    expect(v.reason).toContain("no error handling on the DB call");
  });

  test("no verdict at all → pass (fail-open on a missing sentinel)", () => {
    expect(parseStandardsVerdict("standards judge said nothing").pass).toBe(
      true
    );
  });

  test("a bare FAIL elsewhere does not trip the standards gate", () => {
    expect(
      parseStandardsVerdict("the linter did not FAIL on this diff\n").pass
    ).toBe(true);
  });

  test("the spec sentinel does not trip the standards gate", () => {
    expect(parseStandardsVerdict("SANDCASTLE_SPEC: FAIL — x\n").pass).toBe(true);
  });
});

// The combined helper folds the two isolated judges' verdicts into one gate:
// overall pass only if both axes pass, and it names which axis (or axes) failed
// plus the captured reason so the re-implement pass gets targeted context.
describe("combineVerdicts", () => {
  const pass = { pass: true, reason: "" };

  test("both pass → overall pass, no failing axes", () => {
    expect(combineVerdicts(pass, pass)).toEqual({
      pass: true,
      failedAxes: [],
      reasons: {},
    });
  });

  test("spec fails → overall fail, spec axis named with its reason", () => {
    const spec = { pass: false, reason: "SANDCASTLE_SPEC: FAIL — AC2 missing" };
    const v = combineVerdicts(spec, pass);
    expect(v.pass).toBe(false);
    expect(v.failedAxes).toEqual(["spec"]);
    expect(v.reasons.spec).toContain("AC2 missing");
    expect(v.reasons.standards).toBeUndefined();
  });

  test("standards fails → overall fail, standards axis named", () => {
    const standards = {
      pass: false,
      reason: "SANDCASTLE_STANDARDS: FAIL — unhandled promise",
    };
    const v = combineVerdicts(pass, standards);
    expect(v.pass).toBe(false);
    expect(v.failedAxes).toEqual(["standards"]);
    expect(v.reasons.standards).toContain("unhandled promise");
  });

  test("both fail → overall fail, both axes named in spec-then-standards order", () => {
    const spec = { pass: false, reason: "SANDCASTLE_SPEC: FAIL — a" };
    const standards = { pass: false, reason: "SANDCASTLE_STANDARDS: FAIL — b" };
    const v = combineVerdicts(spec, standards);
    expect(v.pass).toBe(false);
    expect(v.failedAxes).toEqual(["spec", "standards"]);
    expect(v.reasons.spec).toContain("a");
    expect(v.reasons.standards).toContain("b");
  });
});

// classifyReviewedOutcome folds the two verdicts into the terminal outcome the
// run applies: `done` when both pass, or `review-fail` naming the failed axes
// and carrying each failed axis's fuller reviewer stdout (the human's brief for
// re-driving the branch). It absorbs combineVerdicts and the per-axis detail
// assembly that used to sit inline in main's Phase-2 closure. A passing axis's
// detail is dropped even when supplied.
describe("classifyReviewedOutcome", () => {
  const pass = { pass: true, reason: "" };
  const fail = (reason) => ({ pass: false, reason });

  test("both pass → done, no detail carried", () => {
    expect(
      classifyReviewedOutcome(pass, pass, {
        spec: "spec log",
        standards: "standards log",
      })
    ).toEqual({ kind: "done" });
  });

  test("spec fails → review-fail carrying only spec's stdout", () => {
    const out = classifyReviewedOutcome(fail("SANDCASTLE_SPEC: FAIL — AC2"), pass, {
      spec: "full spec reviewer output",
      standards: "full standards output",
    });
    expect(out.kind).toBe("review-fail");
    expect(out.failedAxes).toEqual(["spec"]);
    expect(out.reasons).toEqual({ spec: "full spec reviewer output" });
  });

  test("standards fails → review-fail carrying only standards' stdout", () => {
    const out = classifyReviewedOutcome(
      pass,
      fail("SANDCASTLE_STANDARDS: FAIL — no error handling"),
      { spec: "spec log", standards: "full standards reviewer output" }
    );
    expect(out.kind).toBe("review-fail");
    expect(out.failedAxes).toEqual(["standards"]);
    expect(out.reasons).toEqual({ standards: "full standards reviewer output" });
  });

  test("both fail → both axes named spec-then-standards, both stdouts carried", () => {
    const out = classifyReviewedOutcome(fail("SPEC FAIL"), fail("STD FAIL"), {
      spec: "spec detail",
      standards: "standards detail",
    });
    expect(out.kind).toBe("review-fail");
    expect(out.failedAxes).toEqual(["spec", "standards"]);
    expect(out.reasons).toEqual({
      spec: "spec detail",
      standards: "standards detail",
    });
  });

  test("a missing detail for a failed axis is simply absent, not empty", () => {
    const out = classifyReviewedOutcome(fail("SPEC FAIL"), pass, {});
    expect(out.failedAxes).toEqual(["spec"]);
    expect(out.reasons).toEqual({});
  });
});

// classifyRetryOutcome is classifyReviewedOutcome plus retry awareness (#389).
// Given the two verdicts, the per-axis detail, how many fix-up passes have
// already run (`attempt`, 0 on the first review), and the cap, it decides
// whether to accept the branch, run another fix-up pass, or escalate to a
// human. A pass accepts; a fail retries while attempts remain, else escalates —
// carrying the failed axes and their detail through so the escalation body has
// the human's brief. The re-review is the filter: only a fail the agent cannot
// resolve reaches the cap and escalates.
describe("classifyRetryOutcome", () => {
  const pass = { pass: true, reason: "" };
  const fail = (reason) => ({ pass: false, reason });
  const detail = { spec: "spec log", standards: "standards log" };

  test("both pass → accept, regardless of attempt/cap", () => {
    expect(classifyRetryOutcome(pass, pass, detail, 0, 1)).toEqual({
      kind: "accept",
    });
  });

  test("a fail with attempts remaining → retry, carrying failed axes + detail", () => {
    const out = classifyRetryOutcome(
      pass,
      fail("SANDCASTLE_STANDARDS: FAIL — bare #NNN citation"),
      detail,
      0,
      1
    );
    expect(out.kind).toBe("retry");
    expect(out.failedAxes).toEqual(["standards"]);
    expect(out.reasons).toEqual({ standards: "standards log" });
  });

  test("a fail with the cap reached → escalate, carrying failed axes + detail", () => {
    const out = classifyRetryOutcome(fail("SPEC FAIL"), pass, detail, 1, 1);
    expect(out.kind).toBe("escalate");
    expect(out.failedAxes).toEqual(["spec"]);
    expect(out.reasons).toEqual({ spec: "spec log" });
  });

  test("cap of one: first review retries, the re-review after one fix-up escalates", () => {
    const failed = fail("STD FAIL");
    expect(classifyRetryOutcome(pass, failed, detail, 0, 1).kind).toBe("retry");
    expect(classifyRetryOutcome(pass, failed, detail, 1, 1).kind).toBe(
      "escalate"
    );
  });

  test("cap of two allows a second fix-up pass before escalating", () => {
    const failed = fail("STD FAIL");
    expect(classifyRetryOutcome(pass, failed, detail, 1, 2).kind).toBe("retry");
    expect(classifyRetryOutcome(pass, failed, detail, 2, 2).kind).toBe(
      "escalate"
    );
  });

  test("escalate names both axes and carries both details when both fail", () => {
    const out = classifyRetryOutcome(
      fail("SPEC FAIL"),
      fail("STD FAIL"),
      detail,
      1,
      1
    );
    expect(out.kind).toBe("escalate");
    expect(out.failedAxes).toEqual(["spec", "standards"]);
    expect(out.reasons).toEqual({ spec: "spec log", standards: "standards log" });
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

