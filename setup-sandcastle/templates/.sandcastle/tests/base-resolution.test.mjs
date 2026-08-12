import { test, expect, describe } from "vitest";
import { resolveBase } from "../base-resolution.mts";

// Base resolution collapsed to a single rule: every issue's branch forks from
// `main`. A child is only selected once its parents' issues have closed (their
// PRs merged to main), so its parents' work is already in `main` — nothing to
// stack on, no diamond base to merge. resolveBase is a constant.
describe(".sandcastle base resolution — always main", () => {
  test("resolveBase is main regardless of anything", () => {
    expect(resolveBase()).toBe("main");
  });
});
