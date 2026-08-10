import { test, expect, describe } from "vitest";
import { recordAttempt, recordSetAttempt, REVIEW_RETRY_CAP } from "../retry-policy.mts";

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
    a = recordAttempt(a, "review-issue-7").attempts; // re-implement key
    expect(a).toEqual({ "issue-7": 1, "review-issue-7": 1 });
  });

  // The Phase-3 gate counts consecutive full-suite failures per issue under a
  // gate-<id> key (#25), distinct from the re-review (issue-id) and re-implement
  // (review-<id>) counters so the three caps never interfere for one issue.
  test("gate-<id> counts independently of the other two keys for one issue", () => {
    let a = {};
    a = recordAttempt(a, "7").attempts; // re-review key
    a = recordAttempt(a, "review-7").attempts; // re-implement key
    a = recordAttempt(a, "gate-7").attempts; // gate-failure key
    expect(a).toEqual({ "7": 1, "review-7": 1, "gate-7": 1 });
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

// The Phase-3 gate judges a whole PR set at once: one verdict, one counter per
// member. `recordSetAttempt` folds those per-key results into the single answer
// the caller acts on — did this set escalate (#103)?
describe("recordSetAttempt", () => {
  const keys = ["gate-7", "gate-8"];

  test("a passing verdict clears every key in the set", () => {
    const r = recordSetAttempt({ "gate-7": 1, "gate-8": 1 }, keys, "pass");
    expect(r).toEqual({ attempts: {}, escalated: false });
  });

  test("a passing verdict leaves counters outside the set alone", () => {
    const r = recordSetAttempt({ "gate-7": 1, "review-9": 1 }, keys, "pass");
    expect(r.attempts).toEqual({ "review-9": 1 });
  });

  test("a failing verdict counts one attempt against every key", () => {
    const r = recordSetAttempt({}, keys, "test-fail");
    expect(r).toEqual({ attempts: { "gate-7": 1, "gate-8": 1 }, escalated: false });
  });

  test("reaching the cap escalates, and the escalating key is cleared", () => {
    const r = recordSetAttempt({ "gate-7": 1, "gate-8": 1 }, keys, "test-fail");
    expect(r).toEqual({ attempts: {}, escalated: true });
  });

  // The bug this function exists to make untestable-by-hand: fold with `=`
  // instead of `||=` and the last key's verdict wins. The set fails and passes
  // the gate in lockstep, so its counters normally move together — but
  // recordAttempt deletes a key as it escalates, so counters that ever drifted
  // apart would let a last-wins read miss the escalation and loop the set
  // forever. Only the FIRST key here is at the cap.
  test("escalates when any key hits the cap, not only the last one", () => {
    const r = recordSetAttempt({ "gate-7": 1 }, keys, "test-fail");
    expect(r.escalated).toBe(true);
    expect(r.attempts).toEqual({ "gate-8": 1 });
  });

  // A harness error is an infra fault — a sandbox that never launched says
  // nothing about the code, so it must not spend a retry from the cap.
  test("a harness error counts nothing and escalates nothing", () => {
    const r = recordSetAttempt({ "gate-7": 1 }, keys, "harness-error");
    expect(r).toEqual({ attempts: { "gate-7": 1 }, escalated: false });
  });

  test("is pure — the input map is not mutated", () => {
    const input = { "gate-7": 1, "gate-8": 1 };
    recordSetAttempt(input, keys, "test-fail");
    expect(input).toEqual({ "gate-7": 1, "gate-8": 1 });
  });
});
