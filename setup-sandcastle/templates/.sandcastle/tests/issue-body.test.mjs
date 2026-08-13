import { test, expect } from "vitest";
import {
  spliceReviewFailureSection,
  REVIEW_FAILURE_BEGIN,
  REVIEW_FAILURE_END,
} from "../issue-body.mts";

// spliceReviewFailureSection moved to issue-lifecycle.mts (#274) — the full
// behavior tests moved with it, to tests/issue-lifecycle.test.mjs. This file
// now only proves the compat re-export from this path still resolves and
// works, for anything that still imports "./issue-body.mts".
test("issue-body.mts re-exports the splice from issue-lifecycle.mts", () => {
  const out = spliceReviewFailureSection("body text", "the section");
  expect(out).toContain("body text");
  expect(out).toContain(REVIEW_FAILURE_BEGIN);
  expect(out).toContain(REVIEW_FAILURE_END);
  expect(out).toContain("the section");
});
