// Base-branch resolution.
//
// A child that advances within one run stacks on its parent's branch; every
// other issue forks from `main`. The rule: when the issue has exactly one parent
// that built AND passed review this run, base is that parent's branch — else
// `main`. A root (no parents), a single parent not built this run, and a diamond
// (two or more parents, no single-parent temp-merge in stage one) all fall to
// `main`.
//
// `parents` are the issue's native parent ids. `builtBranches` maps a parent id
// to its branch, but only for parents in the run-scoped built-set — a parent
// absent from the map did not succeed this run. The empty defaults reproduce the
// old constant-`main` behavior, so a caller that passes nothing is unchanged.

export function resolveBase(
  parents: number[] = [],
  builtBranches: Map<number, string> = new Map()
): string {
  if (parents.length !== 1) return "main";
  return builtBranches.get(parents[0]) ?? "main";
}
