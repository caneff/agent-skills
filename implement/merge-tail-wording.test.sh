#!/usr/bin/env bash
# Guards #1145: the controller re-runs the seam on the PR merged onto current
# main before step 3's merge. Guards #1401: § The merge files no sweep and
# disposes of no leftover (no step reviews the diff any more). Prose assertion
# over implement/SKILL.md § The merge.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
[ -n "$merge" ] || { echo "FAIL: could not extract § The merge" >&2; exit 1; }
fail=0
check_in() {
  case "$merge" in *"$1"*) ;; *) echo "FAIL: § The merge is missing: $1" >&2; fail=1 ;; esac
}

# #1401: the controller's merge carries no review step and no per-PR sweep.
check_absent() {
  case "$merge" in *"$1"*) echo "FAIL: § The merge still has: $1" >&2; fail=1 ;; *) ;; esac
}
check_absent 'per-PR sweep'
check_absent 'leftover'
check_absent '`/file-ticket`'

# #1145
check_in 'Before the merge, re-run the seam on the PR as it will land'
check_in 'Run `git fetch origin` first, then skip only when `origin/<default>` has not moved past the PR'"'"'s merge base'
check_in 'git merge-base --is-ancestor origin/<default> <headRefOid>'
check_in 'git worktree add --detach'
check_in 'git merge --no-edit <headRefOid> && <the repo'"'"'s seam>'
check_in '§ End-to-end seam, which is `bash tests/all.sh` here'
check_in 'The controller merges only on green'
check_in 'its next "PR up" restarts at step 2'
check_in 'git worktree remove --force'
check_in 'State the run'"'"'s worker and core count'
check_in "GitHub's CLEAN is a textual-merge verdict, not a test verdict"
check_in "After step 3's re-run of the seam"

# Codex gate on #1172: the merge is bound to the head the seam ran on, and
# the base is re-fetched right before it; both merge lines carry the flag.
check_in 'gh pr merge <pr> --repo <owner/name> --squash --match-head-commit <headRefOid>'
check_in '`git fetch origin` again: when `origin/<default>` is no longer the sha the seam'"'"'s worktree was created from, re-run this step'
brief="$(sed -n '/^## Heavy tier$/,/^### The merge$/p' "$skill" | flatten)"
case "$brief" in *'! gh pr merge <pr> --repo <owner/name> --squash --match-head-commit <headRefOid>'*) ;;
  *) echo "FAIL: the --chris-merges PR-up merge line lacks --match-head-commit" >&2; fail=1 ;; esac
n="$(grep -c 'gh pr merge <pr> --repo <owner/name> --squash' "$skill")"
m="$(grep -c 'gh pr merge <pr> --repo <owner/name> --squash --match-head-commit <headRefOid>' "$skill")"
[ "$n" -eq "$m" ] || { echo "FAIL: a gh pr merge line in SKILL.md lacks --match-head-commit ($m of $n)" >&2; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
