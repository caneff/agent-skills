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

# A leftover .scratch/ is as blocking as a dirty tree, even though it's
# git-ignored and git status stays clean.
mkdir -p "$repo/.scratch"
echo leftover > "$repo/.scratch/leftover.txt"
echo '.scratch/' > "$repo/.gitignore"
git -C "$repo" add .gitignore; git -C "$repo" commit -qm gitignore
tip=$(git -C "$repo" rev-parse HEAD)
run ".scratch/ with content fails the gate" 1 "$tip" ".scratch/"

# The check is repo-wide, not cwd-relative: a worker's shell can sit in a
# subdirectory when it calls the gate by absolute path.
mkdir -p "$repo/sub"
out=$(cd "$repo/sub" && bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *".scratch/"* ]]; then
  echo "PASS: .scratch/ content fails the gate from a subdirectory too"
else
  echo "FAIL: .scratch/ content from a subdirectory — want exit 1 + '.scratch/', got $rc: $out"; fails=1
fi
rmdir "$repo/sub"

# An acknowledged keep: the ticket's escape hatch for content the worker
# cannot commit. The gate warns instead of blocking, and the warning must
# carry the reason so it lands in the PR-up report.
out=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="raw probe log, too big for docs/research" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"raw probe log, too big for docs/research"* ]]; then
  echo "PASS: PRE_REPORT_KEEP_SCRATCH acknowledges a kept .scratch/ and passes"
else
  echo "FAIL: PRE_REPORT_KEEP_SCRATCH — want exit 0 + the reason quoted, got $rc: $out"; fails=1
fi

# The pass line itself — the one line the worker is told to quote — must not
# claim .scratch/ is clear when it was kept, and stdout alone (what a
# captured invocation keeps) must carry the acknowledgement.
stdout_only=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="raw probe log" bash "$gate" "$tip" 2>/dev/null)
if [[ "$stdout_only" != *".scratch/ clear"* ]] && [[ "$stdout_only" == *"kept"* ]]; then
  echo "PASS: the pass line doesn't call a kept .scratch/ clear"
else
  echo "FAIL: pass line on stdout — want no 'clear' claim and a 'kept' mention, got: $stdout_only"; fails=1
fi

# An empty reason isn't an acknowledgement — it's the unset case, so a
# worker that forgets the reason still gets blocked, not silently waved
# through.
out=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *".scratch/"* ]]; then
  echo "PASS: an empty PRE_REPORT_KEEP_SCRATCH still fails the gate"
else
  echo "FAIL: empty PRE_REPORT_KEEP_SCRATCH — want exit 1, got $rc: $out"; fails=1
fi

rm -rf "$repo/.scratch"
mkdir -p "$repo/.scratch"
run "empty .scratch/ dir passes" 0 "$tip"
rmdir "$repo/.scratch"

# Wrong usage is a usage error, not a pass.
out=$(cd "$repo" && bash "$gate" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"usage"* ]]; then
  echo "PASS: no sha argument is a usage error"
else
  echo "FAIL: no sha argument — want exit 2 + usage, got $rc: $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
