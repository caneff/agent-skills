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

# An unreadable .scratch/ must fail closed, not read as empty — root
# ignores directory permissions, so this case is skipped under root.
if [ "$(id -u)" != "0" ]; then
  mkdir -p "$repo/.scratch"
  echo hidden > "$repo/.scratch/hidden.txt"
  chmod 000 "$repo/.scratch"
  out=$(cd "$repo" && bash "$gate" "$tip" 2>&1); rc=$?
  chmod 755 "$repo/.scratch"
  if [ "$rc" = 1 ] && [[ "$out" != *"clear"* ]]; then
    echo "PASS: an unreadable .scratch/ fails closed"
  else
    echo "FAIL: unreadable .scratch/ — want exit 1 and no 'clear' claim, got $rc: $out"; fails=1
  fi
  rm -rf "$repo/.scratch"
else
  echo "SKIP: unreadable .scratch/ case (running as root)"
fi

# The merge check (#1401): on an implement-<n> branch the gate runs
# fix-check.sh, so a finding with no disposition, or a `fixed` sha off
# the branch, stops the worker before "PR up". The check itself has its own
# suite (fix_check_test.py); what is pinned here is that the gate runs it, from a
# linked worktree, and quotes its answer.
git -C "$repo" remote add origin "$repo"
git -C "$repo" fetch -q origin
git -C "$repo" remote set-head origin main
cache_home="$tmp/home"
reviews="$cache_home/.cache/agent-reviews/$(basename "$repo")"
mkdir -p "$reviews"
git -C "$repo" worktree add -q -b implement-7 "$tmp/implement-7" main
echo fix > "$tmp/implement-7/fix.txt"; git -C "$tmp/implement-7" add -A; git -C "$tmp/implement-7" commit -qm fix
wt_tip=$(git -C "$tmp/implement-7" rev-parse HEAD)
wt() { (cd "$tmp/implement-7" && HOME="$cache_home" "$@" bash "$gate" "$wt_tip" 2>&1); }
for a in standards spec correctness; do : >"$reviews/findings-$a-7.jsonl"; : >"$reviews/findings-$a-7.done"; done
# No Codex record, so the ledger must say why (the size gate skipped it).
printf '%s\n' '{"repo": "repo", "ticket": 7, "tickets": [7], "type": "codex-gate", "status": {"fields": {"findings": {"status": "skipped"}}}}' \
  >"$cache_home/.cache/agent-reviews/ledger.jsonl"
printf '%s\n' '{"id": "S1", "axis": "standards", "severity": "hard", "file": "f", "title": "t"}' >"$reviews/findings-standards-7.jsonl"

out=$(wt env); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"no disposition for S1"* ]]; then
  echo "PASS: a finding with no disposition fails the gate, naming the id"
else
  echo "FAIL: undisposed finding — want exit 1 naming S1, got $rc: $out"; fails=1
fi

printf '%s\n' "{\"id\": \"S1\", \"outcome\": \"fixed\", \"sha\": \"$wt_tip\"}" >"$reviews/dispositions-7.jsonl"
out=$(wt env); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"1 findings, each disposed once"* ]]; then
  echo "PASS: a disposed review passes and the pass line quotes the check"
else
  echo "FAIL: disposed review — want exit 0 + the check's line, got $rc: $out"; fails=1
fi

# The Codex lane runs no review wave: it waives the check by naming why, and
# the reason lands in the pass line.
rm "$reviews/dispositions-7.jsonl"
out=$(wt env PRE_REPORT_NO_FIX_CHECK="codex lane, no Claude axes"); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"waived"* ]] && [[ "$out" == *"codex lane, no Claude axes"* ]]; then
  echo "PASS: PRE_REPORT_NO_FIX_CHECK waives the check and quotes the reason"
else
  echo "FAIL: waiver — want exit 0 + 'waived' + reason, got $rc: $out"; fails=1
fi
out=$(wt env PRE_REPORT_NO_FIX_CHECK=""); rc=$?
if [ "$rc" = 1 ]; then
  echo "PASS: an empty PRE_REPORT_NO_FIX_CHECK is not a waiver"
else
  echo "FAIL: empty waiver — want exit 1, got $rc: $out"; fails=1
fi

# A check that could not run (no fix_check.py beside the gate) is an
# environment error, exit 2, never a refusal the worker is told to fix.
mkdir -p "$tmp/lonely/implement"
cp "$gate" "$tmp/lonely/implement/pre-report-gate.sh"
cp "$here/fix-check.sh" "$tmp/lonely/implement/fix-check.sh"
out=$(cd "$tmp/implement-7" && HOME="$cache_home" bash "$tmp/lonely/implement/pre-report-gate.sh" "$wt_tip" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"could not run"* ]]; then
  echo "PASS: a check that cannot run is exit 2, not a refusal"
else
  echo "FAIL: check cannot run — want exit 2 + 'could not run', got $rc: $out"; fails=1
fi
git -C "$repo" worktree remove --force "$tmp/implement-7"

# Off an implement-<n> branch there is no ticket to look a sidecar up by: the
# gate still passes and says the sidecar was not looked for.
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$(git -C "$repo" rev-parse HEAD)" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"not implement-<n>"* ]]; then
  echo "PASS: a non-implement branch passes and says dispositions were not looked for"
else
  echo "FAIL: non-implement branch — want exit 0 + 'not implement-<n>', got $rc: $out"; fails=1
fi

# Wrong usage is a usage error, not a pass.
out=$(cd "$repo" && bash "$gate" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"usage"* ]]; then
  echo "PASS: no sha argument is a usage error"
else
  echo "FAIL: no sha argument — want exit 2 + usage, got $rc: $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
