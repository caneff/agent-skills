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

// The widened signature: resolveBase(parents, builtBranches). `parents` are the
// issue's native parent ids; `builtBranches` maps a parent id to its branch when
// that parent both built and passed review this run. Exactly one parent built
// this run → stack on its branch; anything else (root, unbuilt parent, diamond)
// → `main`. Defaults reproduce today's constant-main behavior.
describe(".sandcastle base resolution — single-parent stacking", () => {
  const built = (obj) => new Map(Object.entries(obj).map(([k, v]) => [+k, v]));

  test("a single parent built this run resolves to the parent's branch", () => {
    expect(resolveBase([1], built({ 1: "sandcastle/issue-1" }))).toBe(
      "sandcastle/issue-1"
    );
  });

  test("a root issue with no parents resolves to main", () => {
    expect(resolveBase([], built({}))).toBe("main");
  });

  test("a single parent not built this run resolves to main", () => {
    expect(resolveBase([1], built({}))).toBe("main");
  });

  test("a diamond with two built parents resolves to main", () => {
    expect(
      resolveBase([1, 2], built({ 1: "sandcastle/issue-1", 2: "sandcastle/issue-2" }))
    ).toBe("main");
  });
});
