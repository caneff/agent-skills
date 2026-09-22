#!/usr/bin/env bash
# Guards #1033: a worker building outside a burn — no run file under it —
# still folds its own small leftover findings into one ticket instead of
# filing each on its own. `implement/SKILL.md` § Review is where the
# leftover outcome itself is defined, so this is where the per-PR sweep
# title, its filing route, and the zero-leftovers case have to be stated —
# the sentence this replaces used to say the sweep "is not built yet".
# BASH_SOURCE rather than `git rev-parse --show-toplevel`: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point that at the caller's repo (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

[ -f "$skill" ] || { echo "FAIL: missing $skill" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### Review' '### Before the PR'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
[ -n "$review" ] || { echo "FAIL: could not extract § Review" >&2; exit 1; }

fail=0
check_in() {
  case "$review" in
    *"$1"*) ;;
    *) echo "FAIL: implement/SKILL.md § Review is missing: $1" >&2; fail=1 ;;
  esac
}

check_in 'no run file'
check_in 'Sweep: leftovers from PR #'
check_in '/file-ticket'
check_in "#1030's body shape"
check_in 'files nothing'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/per-pr-sweep-wording.test.sh"
else
  exit 1
fi
