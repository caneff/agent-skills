#!/usr/bin/env bash
# Did the verification pass (implement/SKILL.md § Review step 2) happen for
# ticket <n>? Run from any checkout of the repo: the review cache is keyed on
# the shared .git's parent name, not the worktree's or the GitHub repo's.
# Exit 0: dispositions-<n>.jsonl holds a line with a bare id (a sweep PR's
# own `<file> <id>` lines do not count), or round 1 provably found
# nothing (all three findings-<axis>-<n>.jsonl exist with no non-blank line,
# so there was nothing to verify). Exit 1 + one line: the pass is missing.
# Exit 2: usage or environment. Used by pre-report-gate.sh (worker) and by
# § The merge step 2 (controller) (#1188).
# Usage: bash verification-check.sh <n>
set -u
n=${1:-}
[[ "$n" =~ ^[0-9]+$ ]] || { echo "usage: verification-check.sh <ticket number>" >&2; exit 2; }
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) ||
  { echo "verification check: not in a git repo" >&2; exit 2; }
reviews="$HOME/.cache/agent-reviews/$(basename "$(dirname "$common")")"
sidecar="$reviews/dispositions-$n.jsonl"

# A sweep PR's worker writes its own `<file> <id>` leftover lines into this
# file (#1259); an id with a space is that, never the verification pass's.
if [ -s "$sidecar" ] && grep -Eq '"id": ?"[^" ]+"' "$sidecar"; then
  echo "dispositions-$n.jsonl present"
  exit 0
fi

# No dispositions: fine only if every axis wrote a findings sidecar and none
# holds a line. An absent or unreadable one is not an empty round.
empty_round=1
for axis in standards spec correctness; do
  f="$reviews/findings-$axis-$n.jsonl"
  if [ ! -r "$f" ] || grep -q '[^[:space:]]' "$f"; then empty_round=0; fi
done
if [ "$empty_round" = 1 ]; then
  echo "round 1 found nothing (all three findings sidecars empty), no verification pass needed"
  exit 0
fi
if [ -e "$sidecar" ]; then
  echo "the dispositions sidecar $sidecar is empty although round 1 has findings — the verification pass recorded no dispositions (implement/SKILL.md § Review step 2)"
else
  echo "no dispositions sidecar at $sidecar — the verification pass (implement/SKILL.md § Review step 2) has not run; run it before reporting"
fi
exit 1
