import { test, expect, describe } from "vitest";
import {
  firstHarnessFault,
  normalizeSettled,
} from "../pipeline-results.mts";

// Pure decisions over the Promise.allSettled array main's Phase 2 produces,
// lifted out of the phase flow so they test without a live sandbox.

const ok = (value) => ({ status: "fulfilled", value });
const bad = (reason) => ({ status: "rejected", reason });
const promptError = "(FiberFailure) PromptError: `!cmd` exited with code 1";

// firstHarnessFault decides whether the whole run aborts: a rejected PromptError
// fails identically for every issue, so it must not be retried per-issue. A
// rejected ordinary error (a sandbox crash, a context blow-up) is per-issue and
// does NOT abort — it normalizes to `nothing` instead.
describe("firstHarnessFault", () => {
  test("no rejections → null", () => {
    expect(firstHarnessFault([ok({ kind: "done" }), ok({ kind: "nothing" })])).toBeNull();
  });

  test("a rejected ordinary error is not a harness fault", () => {
    expect(firstHarnessFault([bad(new Error("context window exceeded"))])).toBeNull();
  });

  test("a rejected PromptError is surfaced", () => {
    expect(firstHarnessFault([ok({ kind: "done" }), bad(promptError)])).toBe(
      promptError
    );
  });

  test("returns the first harness fault when several are present", () => {
    const first = "(FiberFailure) PromptError: first";
    const second = "(FiberFailure) PromptError: second";
    expect(firstHarnessFault([bad(first), bad(second)])).toBe(first);
  });

  test("a crash before the first harness fault does not mask it", () => {
    expect(
      firstHarnessFault([bad(new Error("network")), bad(promptError)])
    ).toBe(promptError);
  });
});

// normalizeSettled projects the settled array to one typed list: a fulfilled
// result passes through; a rejected one (sandbox crash, network) becomes
// `nothing` for the issue recovered by index from `work`.
describe("normalizeSettled", () => {
  const A = { id: "1", branch: "sandcastle/issue-1" };
  const B = { id: "2", branch: "sandcastle/issue-2" };

  test("a fulfilled done passes through unchanged", () => {
    const settled = [ok({ issue: A, kind: "done" })];
    expect(normalizeSettled(settled, [A])).toEqual([{ issue: A, kind: "done" }]);
  });

  test("a fulfilled review-fail carries its axes and reasons through", () => {
    const value = {
      issue: A,
      kind: "review-fail",
      failedAxes: ["spec"],
      reasons: { spec: "detail" },
    };
    expect(normalizeSettled([ok(value)], [A])).toEqual([value]);
  });

  test("a rejected result becomes nothing for the fallback issue by index", () => {
    const settled = [bad(new Error("sandbox crashed"))];
    expect(normalizeSettled(settled, [A])).toEqual([{ issue: A, kind: "nothing" }]);
  });

  test("index alignment is preserved across a mix", () => {
    const settled = [ok({ issue: A, kind: "done" }), bad(new Error("boom"))];
    expect(normalizeSettled(settled, [A, B])).toEqual([
      { issue: A, kind: "done" },
      { issue: B, kind: "nothing" },
    ]);
  });
});
