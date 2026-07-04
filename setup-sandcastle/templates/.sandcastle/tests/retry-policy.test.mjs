import { test, expect, describe } from "vitest";
import { recordAttempt, REVIEW_RETRY_CAP } from "../retry-policy.mts";

describe("recordAttempt", () => {
  test("first failure: counts 1, does not escalate, persists the counter", () => {
    const r = recordAttempt({}, "issue-7");
    expect(r).toEqual({
      attempts: { "issue-7": 1 },
      count: 1,
      escalate: false,
    });
  });

  test("escalates exactly at the cap and clears the counter", () => {
    // cap defaults to 2: first fail persists, second hits the cap.
    const after1 = recordAttempt({}, "issue-7", 2);
    expect(after1).toEqual({
      attempts: { "issue-7": 1 },
      count: 1,
      escalate: false,
    });
    const after2 = recordAttempt(after1.attempts, "issue-7", 2);
    expect(after2).toEqual({ attempts: {}, count: 2, escalate: true });
  });

  test("is pure — the input map is not mutated", () => {
    const input = { "issue-7": 1 };
    recordAttempt(input, "issue-7", 3);
    expect(input).toEqual({ "issue-7": 1 });
  });

  test("distinct keys count independently (review vs spec for one issue)", () => {
    let a = {};
    a = recordAttempt(a, "issue-7").attempts; // review-retry key
    a = recordAttempt(a, "spec-issue-7").attempts; // spec re-implement key
    expect(a).toEqual({ "issue-7": 1, "spec-issue-7": 1 });
  });

  test("honours a custom cap higher than the default", () => {
    let a = {};
    for (let i = 1; i < 5; i++) {
      const r = recordAttempt(a, "k", 5);
      a = r.attempts;
      expect(r.escalate).toBe(false);
      expect(r.count).toBe(i);
    }
    expect(recordAttempt(a, "k", 5)).toEqual({
      attempts: {},
      count: 5,
      escalate: true,
    });
  });
});
