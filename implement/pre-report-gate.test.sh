#!/usr/bin/env bash
# Contract test for pre-report-gate.sh: run inside a throwaway repo, assert
# exit 0 + pass line on a clean tree with an ancestor sha, non-zero + a
# one-line reason on a dirty tree or a sha off the branch.
# Run: bash implement/pre-report-gate.test.sh
set -uo pipefail
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point the repo
# init below at that caller's repo instead of $tmp (#620) — and this test must
# never touch the real skills checkout.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gate="$here/pre-report-gate.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# A throwaway repo: two commits on main, one commit on an abandoned branch.
repo="$tmp/repo"
git init -q -b main "$repo"
git -C "$repo" config user.email t@example.com
git -C "$repo" config user.name t
echo one > "$repo/a.txt"; git -C "$repo" add -A; git -C "$repo" commit -qm one
first=$(git -C "$repo" rev-parse HEAD)
echo two >> "$repo/a.txt"; git -C "$repo" commit -qam two
tip=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" checkout -q -b sidetrack "$first"
echo side > "$repo/b.txt"; git -C "$repo" add -A; git -C "$repo" commit -qm side
offbranch=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" checkout -q main

fails=0
# run <name> <expected-exit> <sha> [<substring the output must contain>]
run() {
  local name=$1 want=$2 sha=$3 needle=${4:-}
  local out rc
  out=$(cd "$repo" && bash "$gate" "$sha" 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL: $name — output missing '$needle'"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

run "clean tree, sha on the branch passes" 0 "$tip" "pre-report gate: clean tree"
run "an older commit on the branch is an ancestor" 0 "$first"
run "a sha off the branch fails" 1 "$offbranch" "not an ancestor"
run "a sha git cannot resolve is exit 2" 2 nosuchsha "cannot resolve"

# Dirty tree: an untracked file is as blocking as a modified one.
echo scratch > "$repo/untracked.txt"
run "untracked file fails the gate" 1 "$tip" "uncommitted"
rm "$repo/untracked.txt"
echo three >> "$repo/a.txt"
run "modified file fails the gate" 1 "$tip" "uncommitted"
git -C "$repo" checkout -q -- a.txt

# Wrong usage is a usage error, not a pass.
out=$(cd "$repo" && bash "$gate" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"usage"* ]]; then
  echo "PASS: no sha argument is a usage error"
else
  echo "FAIL: no sha argument — want exit 2 + usage, got $rc: $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
