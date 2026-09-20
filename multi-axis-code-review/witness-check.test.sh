#!/usr/bin/env bash
# Guards #938 and #939: the hollow-witness check has one owner (correctness),
# and it re-runs the covering suite in a throwaway git worktree rather than
# the whole gate over a whole-tree copy.
# Prose assertions over two skill files; there is no harness that runs a
# skill's own prose.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reviewer="$here/../flow/claude/agents/diff-reviewer.md"

for f in "$skill" "$reviewer"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# Each axis brief scoped to its own bullet block: a needle this generic is
# satisfied by the wrong axis otherwise, which is the whole defect #938 names.
section() { # <file> <start-marker> <end-marker>
  awk -v s="$2" -v e="$3" '
    index($0, s) { on = 1; next }
    on && index($0, e) { exit }
    on { print }
  ' "$1"
}
flatten() { tr '\n' ' ' | tr -s ' '; }

standards="$(section "$skill" '**Standards sub-agent prompt**' '**Spec sub-agent prompt**' | flatten)"
spec="$(section "$skill" '**Spec sub-agent prompt**' '**Correctness sub-agent prompt**' | flatten)"
correctness="$(section "$skill" '**Correctness sub-agent prompt**' 'If the spec is missing' | flatten)"
for pair in "standards:$standards" "spec:$spec" "correctness:$correctness"; do
  [ -n "${pair#*:}" ] || { echo "FAIL: could not extract the ${pair%%:*} axis brief from $skill" >&2; exit 1; }
done

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}
check_not_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) echo "FAIL: $where still carries: $needle" >&2; fail=1 ;;
  esac
}

# #938: one owner. Correctness keeps the check; standards loses it. Two opus
# agents mutating the same tests over the same diff cost two dispositions for
# one finding (#910 round 1 reported S1 and C2 as the same finding).
check_in "$correctness" 'strip the constraint under test' 'the correctness axis brief'
check_not_in "$standards" 'strip the constraint under test' 'the standards axis brief'
check_not_in "$standards" 'hollow witness' 'the standards axis brief'
check_not_in "$spec" 'strip the constraint under test' 'the spec axis brief'

# The count is the assertion a needle cannot make: a witness brief restated
# somewhere else in § 4 is the same duplicated mutation pass.
spawn="$(sed -n '/^###[[:space:]]*4\./,/^###[[:space:]]/{/^###[[:space:]]*4\./d; /^###[[:space:]]/d; p}' "$skill")"
[ -n "$spawn" ] || { echo "FAIL: $skill has no § 4 step" >&2; exit 1; }
witness="$(printf '%s\n' "$spawn" | grep -cF 'strip the constraint under test' || true)"
if [ "$witness" -ne 1 ]; then
  echo "FAIL: § 4 states the witness check in $witness axis briefs, not 1" >&2
  fail=1
fi

# The standing brief names the same one owner: diff-reviewer.md's Axes section
# attaches the check to correctness and to no other axis.
reviewer_witness="$(flatten <"$reviewer" | grep -oF 'strip the constraint under test' | wc -l)"
if [ "$reviewer_witness" -ne 1 ]; then
  echo "FAIL: flow/claude/agents/diff-reviewer.md states the witness check $reviewer_witness times, not 1" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/witness-check.test.sh"
else
  exit 1
fi
