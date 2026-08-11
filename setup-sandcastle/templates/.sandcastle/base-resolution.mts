// Base-branch resolution.
//
// Every issue's branch is cut straight from `main`. A child issue is selected
// only once its parents' issues have closed — their PRs merged to `main` — so by
// the time it builds, all its parents' work is already in `main`. There is
// nothing to stack on and no diamond base to merge, so the base is a constant.
// It stays a named function so the always-main rule has one obvious home and one
// unit test; `issueBranch` is the one surviving naming helper.

export const issueBranch = (id: string): string => `sandcastle/issue-${id}`;

// The base ref an issue's branch is cut from: always `main`. See header.
export function resolveBase(): string {
  return "main";
}
