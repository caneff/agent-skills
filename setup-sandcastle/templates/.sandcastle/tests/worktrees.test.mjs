import { test, expect, describe } from "vitest";
import { parseSandcastleWorktrees } from "../worktrees.mts";

// git worktree list --porcelain sample outputs
const MAIN_ONLY = `worktree /home/user/repo
HEAD abc123
branch refs/heads/main

`;

const WITH_ISSUE_WORKTREE = `worktree /home/user/repo
HEAD abc123
branch refs/heads/main

worktree /home/user/repo/.sandcastle/worktrees/sandcastle-issue-42
HEAD def456
branch refs/heads/sandcastle/issue-42

`;

const WITH_MIXED_WORKTREES = `worktree /home/user/repo
HEAD abc123
branch refs/heads/main

worktree /home/user/repo/.sandcastle/worktrees/sandcastle-issue-7
HEAD bbb111
branch refs/heads/sandcastle/issue-7

worktree /home/user/repo/.sandcastle/pr-head-2026-06-24T12-00-00-1
HEAD ccc222
branch refs/heads/sandcastle/pr-2026-1

worktree /home/user/repo/.sandcastle/worktrees/sandcastle-issue-99
HEAD ddd333
branch refs/heads/sandcastle/issue-99

`;

describe("parseSandcastleWorktrees", () => {
  test("empty output → no paths", () => {
    expect(parseSandcastleWorktrees("")).toEqual([]);
  });

  test("only main worktree → no paths", () => {
    expect(parseSandcastleWorktrees(MAIN_ONLY)).toEqual([]);
  });

  test("one issue worktree → its path returned", () => {
    const paths = parseSandcastleWorktrees(WITH_ISSUE_WORKTREE);
    expect(paths).toEqual([
      "/home/user/repo/.sandcastle/worktrees/sandcastle-issue-42",
    ]);
  });

  test("pr-head worktrees are NOT returned (not under /worktrees/)", () => {
    const paths = parseSandcastleWorktrees(WITH_MIXED_WORKTREES);
    expect(paths.every((p) => p.includes("/.sandcastle/worktrees/"))).toBe(
      true
    );
  });

  test("all issue worktrees are returned, main and pr-head skipped", () => {
    const paths = parseSandcastleWorktrees(WITH_MIXED_WORKTREES);
    expect(paths).toHaveLength(2);
    expect(paths).toContain(
      "/home/user/repo/.sandcastle/worktrees/sandcastle-issue-7"
    );
    expect(paths).toContain(
      "/home/user/repo/.sandcastle/worktrees/sandcastle-issue-99"
    );
  });
});
