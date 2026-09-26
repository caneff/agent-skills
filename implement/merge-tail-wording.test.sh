#!/usr/bin/env bash
# Guards #1125: a Codex-pass leftover on a PR with no run file reaches a sweep
# ticket, because the controller updates or files the per-PR sweep after it
# appends the leftover to the sidecar (§ The merge step 3). Guards #1145: the
# controller re-runs the seam on the PR merged onto current main before step
# 4's merge. Prose assertion over implement/SKILL.md § The merge.
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

# #1125
check_in 'On a PR whose worker brief carried no `--run <run-id>`, appending a Codex `leftover` is not the end'
check_in 'The controller then updates or files the per-PR sweep by § The PR'"'"'s idempotent title search'
check_in 'a non-zero exit from the search stops you and is never read as no hit'
check_in 'no hit files through `/file-ticket`'
check_in 'with the worker'"'"'s existing items kept and the Codex leftovers added'
check_in 'A brief that carried `--run <run-id>` files nothing here'

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
check_in "and step 4's re-run of the seam"

[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
