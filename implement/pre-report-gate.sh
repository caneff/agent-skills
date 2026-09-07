#!/usr/bin/env bash
# The pre-report gate: run from the worktree before reporting a sha.
# Fails unless the tree is clean and <sha> is an ancestor of <tip> — the two
# ways a "done" report has described work that was not on the branch.
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

if ! git merge-base --is-ancestor "$sha" "$tip_sha"; then
  echo "pre-report gate: ${sha:0:12} is not an ancestor of ${tip} (${tip_sha:0:12}) — an amend or a rebase destroyed it" >&2
  exit 1
fi

echo "pre-report gate: clean tree, ${sha:0:12} is an ancestor of ${tip} (${tip_sha:0:12})"
