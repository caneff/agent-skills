// Base-branch resolution for the dependency forest.
//
// Each issue's branch is cut from its "base" — the ref it forks from. The base
// is decided purely from the issue's declared `parents` (the issue ids it builds
// on, emitted by the planner) plus one fact about each parent: does its issue
// branch exist locally with work not already in `main`?
//
//   0 parents                          → `main` (a root chain off main).
//   1 parent, branch present this run  → `sandcastle/issue-<parent>` (stack on it).
//   1 parent, branch absent / merged   → `main` (parent landed in an earlier run;
//                                        its work is already in main, so main is
//                                        the right base and avoids re-importing
//                                        an obsolete branch).
//
// ≥2 parents (diamond / multi-parent) needs a base containing ALL parents.
// resolveBase can't build that itself (it touches no git), so callers inject
// `onMultiParent`, which builds a temp base merging the parents and returns its
// branch name — or `null` if that merge conflicts, so the caller skips the issue
// this iteration instead of building on a wrong base (issue #128). The default
// falls back to `main`, so a mis-declared extra parent degrades to "build on
// main" rather than crashing a caller that didn't supply the hook.
//
// This is a pure function: it takes the parents and a predicate, never touches
// git itself, so it is unit-testable without a repository. The orchestrator
// supplies a real `branchExistsWithWork` backed by `git`.

export const issueBranch = (id: string): string => `sandcastle/issue-${id}`;

export interface ResolveBaseOptions {
  // The issue's declared parent ids (from the planner). Empty for a root.
  parents: string[];
  // True when `sandcastle/issue-<id>` exists locally AND carries work not yet in
  // `main` (i.e. it was built this run and hasn't been merged). False when the
  // branch is absent or its work already landed in main.
  branchExistsWithWork: (parentId: string) => boolean;
  // Invoked for the ≥2-parent (diamond) case. Builds and returns a base branch
  // containing all parents, or `null` if that merge conflicts. Defaults to a safe
  // fall back to `main` when no hook is supplied.
  onMultiParent?: (parents: string[]) => string | null;
}

// Resolve the base ref an issue's branch should be cut from, or `null` when a
// multi-parent base could not be built (the caller skips the issue). See header.
export function resolveBase({
  parents,
  branchExistsWithWork,
  onMultiParent = () => "main",
}: ResolveBaseOptions): string | null {
  if (parents.length === 0) return "main";
  if (parents.length === 1) {
    const [parent] = parents;
    return branchExistsWithWork(parent) ? issueBranch(parent) : "main";
  }
  // ≥2 parents (diamond): the caller's hook builds a temp base merging them.
  return onMultiParent(parents);
}

// Git operations buildMultiParentBase needs, injected so the merge-loop logic is
// unit-testable with a fake git (the real one lives in the orchestrator).
export interface MultiParentDeps {
  // Run a git command; returns its output, or null when the command fails (e.g. a
  // conflicting merge). Mirrors the orchestrator's `git()` helper.
  git: (args: string) => string | null;
  // Whether a parent's issue branch exists locally with unmerged work this run.
  branchExistsWithWork: (parentId: string) => boolean;
}

// Build a temp base branch for a multi-parent (diamond) issue: one containing
// every parent's work. Start from `main` (which already holds any parent merged
// in an earlier run) and merge in each parent whose branch still carries unmerged
// work this run. Returns the temp branch name, or null if any merge conflicts —
// the caller then skips the issue this iteration rather than building on a base
// missing a parent. A diamond whose parents all already merged needs no temp
// branch and resolves straight to `main`.
//
// NB: we branch from `main` and merge the present parents, rather than branching
// from the first parent and merging the rest — equivalent result, and starting at
// main keeps the base run-scope-correct when some parents already merged.
export function buildMultiParentBase(
  issueId: string,
  parents: string[],
  { git, branchExistsWithWork }: MultiParentDeps
): string | null {
  const present = parents.filter(branchExistsWithWork).map(issueBranch);
  if (present.length === 0) return "main";
  const baseBranch = `sandcastle/base-${issueId}`;
  git(`branch -f ${baseBranch} main`);
  const wt = `.sandcastle/base-${issueId}`;
  git(`worktree remove --force ${wt}`); // clear any stale scratch worktree
  git(`worktree add --force ${wt} ${baseBranch}`);
  let ok = true;
  for (const branch of present) {
    const merged = git(
      `-C ${wt} merge --no-edit -m "Merge ${branch} into ${baseBranch}" ${branch}`
    );
    if (merged === null) {
      git(`-C ${wt} merge --abort`);
      ok = false;
      break;
    }
  }
  git(`worktree remove --force ${wt}`);
  return ok ? baseBranch : null;
}
