import { test, expect, describe } from "vitest";
import { resolveBase, issueBranch } from "../base-resolution.mts";

// Base resolution collapsed to a single rule: every issue's branch forks from
// `main`. A child is only selected once its parents' issues have closed (their
// PRs merged to main), so its parents' work is already in `main` — nothing to
// stack on, no diamond base to merge. resolveBase is a constant; issueBranch is
// the one surviving naming helper.
describe(".sandcastle base resolution — always main", () => {
  test("resolveBase is main regardless of anything", () => {
    expect(resolveBase()).toBe("main");
  });

  test("issueBranch names the per-issue branch", () => {
    expect(issueBranch("112")).toBe("sandcastle/issue-112");
    expect(issueBranch("108")).toBe("sandcastle/issue-108");
  });
});
