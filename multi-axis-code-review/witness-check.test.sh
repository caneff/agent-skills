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

# #939, first cost: the brief never said what to re-run, so an axis could take
# `bash tests/all.sh` (2m51s wall, 62 suites) once per mutated test. It names
# the covering suite, and says the whole gate is not this axis's to re-run.
check_in "$correctness" 'the suite that covers' 'the correctness axis brief'
check_in "$correctness" 'not the whole gate' 'the correctness axis brief'

# #939, second cost: isolation by throwaway worktree, not by copying a
# 419 MB / 529-file tree once per mutated test.
check_in "$correctness" 'git worktree add' 'the correctness axis brief'
check_not_in "$correctness" 'scratch copy of the tree' 'the correctness axis brief'
check_in "$correctness" 'worktree remove' 'the correctness axis brief'
# The standing brief says the same, since an axis reads it whether or not the
# caller's paste survived.
reviewer_text="$(flatten <"$reviewer")"
check_in "$reviewer_text" 'worktree' flow/claude/agents/diff-reviewer.md
check_not_in "$reviewer_text" 'a witness check runs on a copy' flow/claude/agents/diff-reviewer.md

# Prose can claim isolation; only running the documented recipe witnesses it.
# Extracting it out of SKILL.md rather than retyping it here is what keeps the
# test honest — a copy in this file would pass forever while the doc drifted.
recipe="$(awk '
  /^```$/ { if (inb) { if (buf ~ /worktree add --detach/) printf "%s", buf; buf = ""; inb = 0 }
            else inb = 1
            next }
  inb { buf = buf $0 "\n" }
' "$skill")"
case "$recipe" in
  *'worktree add --detach'*) ;;
  *) echo "FAIL: could not extract the witness-isolation recipe from $skill" >&2; exit 1 ;;
esac

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'rm -rf "$scratch"' EXIT
(
  cd "$scratch"
  git init -q -b main repo
  cd repo
  git config user.email t@example.com
  git config user.name t
  printf 'assert 1 == 1\n' >t.py
  git add t.py
  git commit -qm base
) || { echo "FAIL: could not build the scratch repo" >&2; exit 1; }
repo="$scratch/repo"

# The recipe's placeholders are an assignment and a one-line comment, so real
# values substitute in without touching any other line of what the doc
# publishes.
printf '%s\n' "$recipe" |
  sed -e "s|^worktree=<.*|worktree=$repo|" \
      -e "s|^# <strip the constraint.*|printf 'assert 1 == 2\\n' >\"\$witness\"/t.py; echo \"\$witness\" >\"$scratch/where\"|" \
  >"$scratch/recipe.sh"
( cd "$repo" && bash "$scratch/recipe.sh" ) || {
  echo "FAIL: the documented witness-isolation recipe did not run" >&2; fail=1; }

if [ "$(cat "$repo/t.py")" != 'assert 1 == 1' ]; then
  echo "FAIL: the witness recipe wrote the mutation back into the checkout" >&2
  fail=1
fi
if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo "FAIL: the witness recipe left the checkout dirty" >&2
  fail=1
fi
# A worktree left registered stalls the next `git worktree remove` and any
# later `merge-cleanup` on this repo; a bare `rm -rf` would leave exactly that.
trees="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees" -ne 1 ]; then
  echo "FAIL: the witness recipe left $trees worktrees registered, not 1" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi
if [ -e "$(cat "$scratch/where" 2>/dev/null)" ]; then
  echo "FAIL: the witness recipe left its throwaway worktree on disk" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/witness-check.test.sh"
else
  exit 1
fi
