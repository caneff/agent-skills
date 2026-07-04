// Parses `git worktree list --porcelain` output.
export function parseSandcastleWorktrees(porcelainOutput: string): string[] {
  return [...porcelainOutput.matchAll(/^worktree (.+)$/gm)]
    .map((m) => m[1])
    .filter((path) => path.includes("/.sandcastle/worktrees/"));
}
