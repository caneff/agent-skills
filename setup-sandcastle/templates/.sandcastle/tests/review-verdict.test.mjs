import { test, expect, describe } from "vitest";
import {
  parseSpecVerdict,
  parseStandardsVerdict,
  combineVerdicts,
  isHarnessError,
  parseCheckVerdict,
} from "../review-verdict.mts";

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

// The standards judge emits its own sentinel line, gated identically to spec:
// only an explicit `SANDCASTLE_STANDARDS: FAIL` blocks; PASS or a missing
// sentinel is fail-open. (Ticket #2 — additive parsing, nothing wired yet.)
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

// Unlike the reviewer verdicts (an agent opinion, fail-OPEN on a missing
// sentinel), the full-suite gate is a safety gate and fails CLOSED: a `pass`
// requires the affirmative `SANDCASTLE_CHECK: PASS` sentinel the gate wrapper
// echoes only when `just check` exits zero. Anything else is `test-fail`.
describe("parseCheckVerdict", () => {
  test("a green run (PASS sentinel present) → pass, no tail", () => {
    const out = [
      "✓ tests/foo.test.mjs (3)",
      "Test Files  4 passed (4)",
      "SANDCASTLE_CHECK: PASS",
    ].join("\n");
    expect(parseCheckVerdict(out)).toEqual({ status: "pass", tail: "" });
  });

  test("a failing run (no PASS sentinel) → test-fail, tail names the failing tests", () => {
    const out = [
      "RUN  v4.1.9",
      " ✓ tests/math.test.mjs (2)",
      " FAIL  tests/auth.test.mjs > login rejects an expired token",
      " FAIL  tests/auth.test.mjs > logout clears the session",
      "AssertionError: expected 401 to be 200",
      "Test Files  1 failed | 1 passed (2)",
    ].join("\n");
    const v = parseCheckVerdict(out);
    expect(v.status).toBe("test-fail");
    expect(v.tail).toContain("login rejects an expired token");
    expect(v.tail).toContain("logout clears the session");
  });

  test("a huge failing log is bounded — the whole thing never passes through", () => {
    const huge = Array.from(
      { length: 5000 },
      (_, i) => ` FAIL  tests/big.test.mjs > case ${i}`
    ).join("\n");
    const v = parseCheckVerdict(huge);
    expect(v.status).toBe("test-fail");
    expect(v.tail.split("\n").length).toBeLessThanOrEqual(60);
    // The failing tail is a small fraction of the 5000-line log.
    expect(v.tail.length).toBeLessThan(huge.length / 10);
  });

  test("empty output fails CLOSED → test-fail (a crashed check is not green)", () => {
    expect(parseCheckVerdict("").status).toBe("test-fail");
  });

  test("garbled output with no sentinel fails CLOSED → test-fail", () => {
    expect(parseCheckVerdict("\x00\x00 sandbox died mid-run \x00").status).toBe(
      "test-fail"
    );
  });

  test("a harness/sandbox fault → harness-error, NOT test-fail", () => {
    const out =
      "seeding venv...\n(FiberFailure) PromptError: Command `just check` failed to launch: sandbox unavailable";
    expect(parseCheckVerdict(out).status).toBe("harness-error");
  });

  test("a real test failure is NOT misread as a harness fault", () => {
    const out = " FAIL  tests/auth.test.mjs > token check\nExpected 1 to be 2";
    expect(parseCheckVerdict(out).status).toBe("test-fail");
  });
});
