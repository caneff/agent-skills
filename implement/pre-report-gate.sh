#!/usr/bin/env bash
# The pre-report gate: run from the worktree before reporting a sha.
# Fails unless the tree is clean, <sha> is an ancestor of <tip>, the
# workspace's .scratch/ is empty, and — on an implement-<n> branch — the review
# cache shows the verification pass ran (#1188: verification-check.sh) and the PR body
# pr-body-<n>.md exists and its Decisions made agrees with that sidecar
# (#1214): the ways a "done" report has described work that was not on the
# branch, left cleanup for later, skipped the verification pass, or shipped a
# stale disposition.
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
if [ -d "$scratch_dir" ]; then
  scratch_listing=$(ls -A "$scratch_dir" 2>&1)
  ls_rc=$?
  if [ "$ls_rc" -ne 0 ]; then
    echo "pre-report gate: .scratch/ exists but could not be read (ls exit $ls_rc) — fix its permissions or remove it before reporting: $scratch_listing" >&2
    exit 1
  fi
  if [ -n "$scratch_listing" ]; then
    if [ -n "${PRE_REPORT_KEEP_SCRATCH:-}" ]; then
      scratch_status=".scratch/ kept, acknowledged: $PRE_REPORT_KEEP_SCRATCH"
    else
      echo "pre-report gate: .scratch/ still has content — commit any reusable finding into docs/research/ (or the relevant note) and delete .scratch/, or set PRE_REPORT_KEEP_SCRATCH=\"<why>\" and name it in the PR-up report" >&2
      exit 1
    fi
  fi
fi

if ! git merge-base --is-ancestor "$sha" "$tip_sha"; then
  echo "pre-report gate: ${sha:0:12} is not an ancestor of ${tip} (${tip_sha:0:12}) — an amend or a rebase destroyed it" >&2
  exit 1
fi

# The dispositions check (#1214, #1188): on an implement-<n> branch the review
# cache must hold dispositions-<n>.jsonl, and the PR body's Decisions made must
# agree with it — the comparison `runfile.py leftover` makes at harvest, made here
# so the worker rewrites a stale line instead of the controller. Off an
# implement-<n> branch there is no ticket to look up, and the pass line says so.
branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" =~ ^implement-([0-9]+)$ ]]; then
  n=${BASH_REMATCH[1]}
  common=$(git rev-parse --path-format=absolute --git-common-dir) ||
    { echo "pre-report gate: cannot resolve the common .git" >&2; exit 2; }
  reviews="$HOME/.cache/agent-reviews/$(basename "$(dirname "$common")")"
  sidecar="$reviews/dispositions-$n.jsonl"
  body="$reviews/pr-body-$n.md"
  # A heavy build's verification pass writes the sidecar (#1188); verification-check.sh
  # refuses a missing one unless round 1 provably found nothing. The Codex lane
  # writes none and waives it by naming why. Light tier never runs this gate.
  if [ -n "${PRE_REPORT_NO_VERIFICATION:-}" ]; then
    verification="verification pass waived, acknowledged: $PRE_REPORT_NO_VERIFICATION"
  else
    verification=$(bash "$(dirname "${BASH_SOURCE[0]}")/verification-check.sh" "$n" 2>&1)
    vrc=$?
    [ "$vrc" -ne 1 ] || { echo "pre-report gate: $verification" >&2; exit 1; }
    [ "$vrc" -eq 0 ] || { echo "pre-report gate: verification-check.sh could not run (exit $vrc): $verification" >&2; exit 2; }
  fi
  dispositions_status="$verification"
  # Nothing to compare the PR body against when no sidecar was written.
  if [ -s "$sidecar" ]; then
    [ -f "$body" ] || { echo "pre-report gate: $sidecar exists but the PR body $body does not — write the body there first (implement/SKILL.md § The PR)" >&2; exit 1; }
    runfile="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../burndown/runfile.py"
    check=$(python3 "$runfile" check --from "$sidecar" --pr-body "$body" 2>&1)
    check_rc=$?
    [ "$check_rc" -le 1 ] ||
      { echo "pre-report gate: runfile.py check could not run (exit $check_rc): $check" >&2; exit 2; }
    [ "$check_rc" -eq 0 ] ||
      { echo "pre-report gate: runfile.py check refused — fix the sidecar line or the body's line (the gate has no --allow-stale; that flag is harvest's): $check" >&2; exit 1; }
    dispositions_status="$verification; dispositions agree with the PR body"
  fi
else
  dispositions_status="branch '$branch' is not implement-<n>, dispositions not looked for"
fi

echo "pre-report gate: clean tree, ${scratch_status}, ${dispositions_status}, ${sha:0:12} is an ancestor of ${tip} (${tip_sha:0:12})"
