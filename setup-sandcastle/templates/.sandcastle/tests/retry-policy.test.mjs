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

  // The Phase-3 gate counts consecutive full-suite failures per issue under a
  // gate-<id> key (#25), distinct from the review (issue-id) and spec (spec-<id>)
  // counters so the three caps never interfere for one issue.
  test("gate-<id> counts independently of review and spec keys for one issue", () => {
    let a = {};
    a = recordAttempt(a, "7").attempts; // review-retry key
    a = recordAttempt(a, "spec-7").attempts; // spec re-implement key
    a = recordAttempt(a, "gate-7").attempts; // gate-failure key
    expect(a).toEqual({ "7": 1, "spec-7": 1, "gate-7": 1 });
  });

  test("gate-<id> escalates at cap 2 (second consecutive failure)", () => {
    const first = recordAttempt({}, "gate-7", 2);
    expect(first).toMatchObject({ count: 1, escalate: false });
    const second = recordAttempt(first.attempts, "gate-7", 2);
    expect(second).toEqual({ attempts: {}, count: 2, escalate: true });
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
