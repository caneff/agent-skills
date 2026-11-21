#!/usr/bin/env bash
# The pre-report gate: run from the worktree before reporting a sha.
# Fails unless the tree is clean, <sha> is an ancestor of <tip>, and — on an implement-<n> branch, or a spec
# run's spec-<n> keyed on the spec number — the merge check (fix-check.sh)
# passes: every review finding has one disposition, a `fixed` sha is a
# commit on the branch, a `moved` ticket is open: the ways a "done" report
# has described work that was not on the branch, left cleanup for later,
# or dropped a finding. A slice of a spec run, its base recorded as
# spec-<p>, has no review to dispose of, and fix-check.sh says so; every
# other check here still runs. The workspace's .scratch/ is not checked:
# merge-cleanup discards it once the branch has landed (#1699).
# PRE_REPORT_TREE_ONLY=1 stops after the clean-tree check (exit 0 + a pass
# line): the Stop hook worker-dirty-stop.sh (#1907) runs it on every worker
# stop, where a stop for a question has no sha, scratch or dispositions yet.
# Usage: bash pre-report-gate.sh <sha> [<tip, default HEAD>]
# Exit 0 + a pass line to quote in the report; 1 + a one-line reason; 2 on
# usage or a sha git cannot resolve.
set -u

sha=${1:-}
tip=${2:-HEAD}
[ -n "$sha" ] || { echo "usage: pre-report-gate.sh <sha> [<tip, default HEAD>]" >&2; exit 2; }

git rev-parse --git-dir >/dev/null 2>&1 || { echo "pre-report gate: not a git repo" >&2; exit 2; }
sha=$(git rev-parse --verify --quiet "$sha^{commit}") ||
  { echo "pre-report gate: cannot resolve '${1}' to a commit" >&2; exit 2; }
tip_sha=$(git rev-parse --verify --quiet "$tip^{commit}") ||
  { echo "pre-report gate: cannot resolve '$tip' to a commit" >&2; exit 2; }

dirty=$(git status --porcelain)
if [ -n "$dirty" ]; then
  echo "pre-report gate: uncommitted or untracked files — commit or remove them:" >&2
  printf '%s\n' "$dirty" >&2
  exit 1
fi

if [ -n "${PRE_REPORT_TREE_ONLY:-}" ]; then
  echo "pre-report gate: clean tree (tree-only check)"
  exit 0
fi

top=$(git rev-parse --show-toplevel) || { echo "pre-report gate: cannot resolve the repo root" >&2; exit 2; }
# `.scratch/` is not checked (#1699): merge-cleanup discards it and lists
# each file once the branch has landed. The status only says what is left.
scratch_status=".scratch/ clear"
if [ -n "$(ls -A "$top/.scratch" 2>/dev/null)" ]; then
  scratch_status=".scratch/ left for merge-cleanup"
fi

if ! git merge-base --is-ancestor "$sha" "$tip_sha"; then
  echo "pre-report gate: ${sha:0:12} is not an ancestor of ${tip} (${tip_sha:0:12}) — an amend or a rebase destroyed it" >&2
  exit 1
fi

# The merge check: on an implement-<n> branch every review finding of ticket
# <n> is disposed (fix-check.sh), and on a spec run's spec-<n> every finding
# of the spec review, keyed on the spec number. Off those branches there
# is no ticket to look up, and the pass line says so.
branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" =~ ^(implement|spec)-([0-9]+)$ ]]; then
  n=${BASH_REMATCH[2]}
  # The Codex lane runs no review wave and waives the check by naming why.
  # Light tier never runs this gate.
  if [ -n "${PRE_REPORT_NO_FIX_CHECK:-}" ]; then
    dispositions_status="fix check waived, acknowledged: $PRE_REPORT_NO_FIX_CHECK"
  else
    check=$(bash "$(dirname "${BASH_SOURCE[0]}")/fix-check.sh" "$n" "$branch" 2>&1)
    rc=$?
    [ "$rc" -ne 1 ] || { echo "pre-report gate: $check" >&2; exit 1; }
    [ "$rc" -eq 0 ] || { echo "pre-report gate: fix-check.sh could not run (exit $rc): $check" >&2; exit 2; }
    dispositions_status="$check"
  fi
else
  dispositions_status="branch '$branch' is not implement-<n> or spec-<n>, dispositions not looked for"
fi

echo "pre-report gate: clean tree, ${scratch_status}, ${dispositions_status}, ${sha:0:12} is an ancestor of ${tip} (${tip_sha:0:12})"
