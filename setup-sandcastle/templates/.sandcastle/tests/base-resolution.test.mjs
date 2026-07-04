import { test, expect, describe } from "vitest";
import {
  resolveBase,
  issueBranch,
  buildMultiParentBase,
} from "../base-resolution.mts";

// Fixture forest (from issue #126):
//   108 builds on 112        → chain  main ─ 112 ─ 108
//   120 builds on 119        → chain  main ─ 119 ─ 120
//   112, 119 are independent roots off main
//
// All four complete in the SAME run, so each parent branch exists locally with
// work not yet in main. Base resolution must put 108 on 112's branch and 120 on
// 119's branch, while 112 and 119 sit on main — proving the two chains stay
// independent off main with no cross-chain interleaving.

const parentsOf = {
  108: ["112"],
  120: ["119"],
  112: [],
  119: [],
};

describe(".sandcastle base resolution — forest fixture 108→112, 120→119", () => {
  // Every issue branch from this run exists locally with work.
  const allBuiltThisRun = () => true;

  test("root 112 resolves to main (no parents)", () => {
    expect(
      resolveBase({
        parents: parentsOf["112"],
        branchExistsWithWork: allBuiltThisRun,
      })
    ).toBe("main");
  });

  test("root 119 resolves to main (no parents)", () => {
    expect(
      resolveBase({
        parents: parentsOf["119"],
        branchExistsWithWork: allBuiltThisRun,
      })
    ).toBe("main");
  });

  test("108 resolves to its parent 112's branch (1 parent, present this run)", () => {
    expect(
      resolveBase({
        parents: parentsOf["108"],
        branchExistsWithWork: allBuiltThisRun,
      })
    ).toBe(issueBranch("112"));
  });

  test("120 resolves to its parent 119's branch (1 parent, present this run)", () => {
    expect(
      resolveBase({
        parents: parentsOf["120"],
        branchExistsWithWork: allBuiltThisRun,
      })
    ).toBe(issueBranch("119"));
  });

  test("1-parent issue falls back to main when the parent already merged (branch absent / no work)", () => {
    // Parent landed in an earlier run: its work is in main, branch carries no
    // unmerged work. Base is main, not a stale parent branch.
    const base = resolveBase({
      parents: ["112"],
      branchExistsWithWork: () => false,
    });
    expect(base).toBe("main");
  });

  test("≥2 parents with no hook falls back to main", () => {
    expect(
      resolveBase({
        parents: ["112", "119"],
        branchExistsWithWork: allBuiltThisRun,
      })
    ).toBe("main");
  });

  test("≥2 parents (diamond) delegates to onMultiParent and returns its base", () => {
    let seen;
    const base = resolveBase({
      parents: ["112", "119"],
      branchExistsWithWork: allBuiltThisRun,
      onMultiParent: (ps) => {
        seen = ps;
        return "sandcastle/base-130";
      },
    });
    expect(seen).toEqual(["112", "119"]);
    expect(base).toBe("sandcastle/base-130");
  });

  test("a conflicting multi-parent merge propagates null so the caller can skip", () => {
    expect(
      resolveBase({
        parents: ["112", "119"],
        branchExistsWithWork: allBuiltThisRun,
        onMultiParent: () => null,
      })
    ).toBeNull();
  });
});

// buildMultiParentBase — the git-touching half (issue #128), driven through a
// fake `git` so the merge-loop logic (which parents get merged, conflict → abort
// → null, all-merged → main) is verified without a real repository.
describe("buildMultiParentBase — temp base for a diamond", () => {
  // Records every git command; returns null (failure) for a merge of the branch
  // named in `conflictOn`, "" (success) otherwise.
  const fakeGit = (conflictOn = null) => {
    const calls = [];
    const git = (args) => {
      calls.push(args);
      if (conflictOn && args.includes("merge ") && args.includes(conflictOn)) {
        return null;
      }
      return "";
    };
    return { git, calls };
  };
  const merges = (calls) => calls.filter((c) => c.includes("merge --no-edit"));

  test("all parents already merged → main, no git touched", () => {
    const { git, calls } = fakeGit();
    const base = buildMultiParentBase("130", ["112", "119"], {
      git,
      branchExistsWithWork: () => false,
    });
    expect(base).toBe("main");
    expect(calls).toEqual([]);
  });

  test("merges EVERY present parent and returns the temp base branch", () => {
    const { git, calls } = fakeGit();
    const base = buildMultiParentBase("130", ["112", "119"], {
      git,
      branchExistsWithWork: () => true,
    });
    expect(base).toBe("sandcastle/base-130");
    expect(merges(calls).length).toBe(2);
    expect(merges(calls).some((c) => c.includes("sandcastle/issue-112"))).toBe(
      true
    );
    expect(merges(calls).some((c) => c.includes("sandcastle/issue-119"))).toBe(
      true
    );
    expect(calls.some((c) => c.includes("merge --abort"))).toBe(false);
  });

  test("a parent already in main is skipped, present ones still merged", () => {
    const { git, calls } = fakeGit();
    const base = buildMultiParentBase("130", ["112", "119"], {
      git,
      branchExistsWithWork: (id) => id === "112",
    });
    expect(base).toBe("sandcastle/base-130");
    expect(merges(calls).length).toBe(1);
    expect(merges(calls)[0]).toContain("sandcastle/issue-112");
  });

  test("a conflicting merge aborts and returns null (caller skips)", () => {
    const { git, calls } = fakeGit("sandcastle/issue-119");
    const base = buildMultiParentBase("130", ["112", "119"], {
      git,
      branchExistsWithWork: () => true,
    });
    expect(base).toBeNull();
    expect(calls.some((c) => c.includes("merge --abort"))).toBe(true);
  });
});
