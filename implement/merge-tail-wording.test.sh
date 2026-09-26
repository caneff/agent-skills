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
check_in 'The controller then updates or files the per-PR sweep through § The PR'"'"'s idempotent title search'
check_in 'A burn PR files nothing here'

# #1145
check_in 'Before the merge, re-run the seam on the PR as it will land'
check_in '`origin/<default>` has not moved past the PR'"'"'s merge base'
check_in 'git worktree add --detach'
check_in 'bash tests/all.sh'
check_in 'merges only on green'
check_in 'State the worker and core budget'
check_in "GitHub's CLEAN is a textual-merge verdict, not a test verdict"

[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
