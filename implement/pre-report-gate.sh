#!/usr/bin/env bash
# The pre-report gate: run from the worktree before reporting a sha.
# Fails unless the tree is clean, <sha> is an ancestor of <tip>, and the
# workspace's .scratch/ is empty — the three ways a "done" report has
# described work that was not on the branch or left cleanup for later.
# A non-empty .scratch/ the worker cannot commit and must keep is named in
# the PR-up report by setting PRE_REPORT_KEEP_SCRATCH="<why>", which passes
# the check and folds the reason into the pass line itself.
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

top=$(git rev-parse --show-toplevel) || { echo "pre-report gate: cannot resolve the repo root" >&2; exit 2; }
scratch_dir="$top/.scratch"
scratch_status=".scratch/ clear"
if [ -d "$scratch_dir" ] && [ -n "$(ls -A "$scratch_dir" 2>/dev/null)" ]; then
  if [ -n "${PRE_REPORT_KEEP_SCRATCH:-}" ]; then
    scratch_status=".scratch/ kept, acknowledged: $PRE_REPORT_KEEP_SCRATCH"
  else
    echo "pre-report gate: .scratch/ still has content — commit any reusable finding into docs/research/ (or the relevant note) and delete .scratch/, or set PRE_REPORT_KEEP_SCRATCH=\"<why>\" and name it in the PR-up report" >&2
    exit 1
  fi
fi

if ! git merge-base --is-ancestor "$sha" "$tip_sha"; then
  echo "pre-report gate: ${sha:0:12} is not an ancestor of ${tip} (${tip_sha:0:12}) — an amend or a rebase destroyed it" >&2
  exit 1
fi

echo "pre-report gate: clean tree, ${scratch_status}, ${sha:0:12} is an ancestor of ${tip} (${tip_sha:0:12})"
