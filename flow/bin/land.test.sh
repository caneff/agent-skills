#!/usr/bin/env bash
# Command-line contract test for `land`. Builds throwaway repos under mktemp
# with a file-path bare origin (so no network, no gh, no real GitHub repo) and
# checks what reaches the origin and what remains on disk.
# Run: bash flow/bin/land.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
land="$here/land"

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
fails=0

# Each case gets its own origin/clone/worktree triple under $root/<name>.
# $origin is bare, $clone has main checked out, $wt is a linked worktree on
# branch `feature`. Leaves the caller with those three vars set.
setup() {
    local name=$1
    origin="$root/$name/origin.git"
    clone="$root/$name/clone"
    wt="$root/$name/wt"
    mkdir -p "$root/$name"
    git init --bare -q -b main "$origin"
    git clone -q "$origin" "$clone"
    git -C "$clone" config user.email land@test.invalid
    git -C "$clone" config user.name "Land Test"
    echo base > "$clone/file.txt"
    git -C "$clone" add -A
    git -C "$clone" commit -qm "initial"
    git -C "$clone" push -q -u origin main
    git -C "$clone" worktree add -q -b feature "$wt" main
    git -C "$clone" config land.testcmd true
}

# Commit on main in the clone and push, so origin/main is ahead of the branch.
advance_main() {
    printf '%s\n' "$2" > "$clone/$1"
    git -C "$clone" add -A
    git -C "$clone" commit -qm "main: $1"
    git -C "$clone" push -q origin main
}

commit_on_feature() {
    printf '%s\n' "$2" > "$wt/$1"
    git -C "$wt" add -A
    git -C "$wt" commit -qm "feature: $1"
}

check() {
    if [ "$2" = "$3" ]; then
        echo "  ok: $1"
    else
        echo "  FAIL: $1"
        echo "    want: $2"
        echo "    got:  $3"
        fails=$((fails + 1))
    fi
}

run_land() { (cd "$wt" && bash "$land" 2>&1); }

echo "case: happy path"
setup happy
advance_main other.txt hello
commit_on_feature feat.txt one
before=$(git -C "$origin" rev-parse main)
out=$(run_land); rc=$?
check "exit 0" 0 "$rc"
check "feature file on origin main" one \
    "$(git -C "$origin" show main:feat.txt 2>/dev/null)"
check "main's own commit still on origin" hello \
    "$(git -C "$origin" show main:other.txt 2>/dev/null)"
check "linear history (no merges)" "" \
    "$(git -C "$origin" log --merges --format=%H main)"
check "rebased: the feature commit sits directly on old main" "$before" \
    "$(git -C "$origin" rev-parse main^ 2>/dev/null)"
check "worktree directory gone" gone "$([ -d "$wt" ] || echo gone)"
check "worktree deregistered" "" \
    "$(git -C "$clone" worktree list --porcelain | grep -F "worktree $wt" || true)"
[ "$rc" -eq 0 ] || echo "$out" | sed 's/^/    /'

echo "case: tests fail"
setup testfail
git -C "$clone" config land.testcmd false
before=$(git -C "$origin" rev-parse main)
commit_on_feature feat.txt one
out=$(run_land); rc=$?
check "nonzero exit" nonzero "$([ "$rc" -ne 0 ] && echo nonzero)"
check "origin main untouched" "$before" "$(git -C "$origin" rev-parse main)"
check "worktree still there" here "$([ -d "$wt" ] && echo here)"
check "message names the tests" named \
    "$(echo "$out" | grep -qi test && echo named)"

echo "case: rebase conflict"
setup conflict
commit_on_feature file.txt feature-side
feat_sha=$(git -C "$wt" rev-parse HEAD)
advance_main file.txt main-side
before=$(git -C "$origin" rev-parse main)
out=$(run_land); rc=$?
check "nonzero exit" nonzero "$([ "$rc" -ne 0 ] && echo nonzero)"
check "origin main untouched" "$before" "$(git -C "$origin" rev-parse main)"
check "branch restored to pre-rebase commit" "$feat_sha" "$(git -C "$wt" rev-parse HEAD)"
check "no rebase left in progress" "" \
    "$(git -C "$wt" status --porcelain=v2 --branch | grep -F 'rebase' || true)"
check "stop-and-report message" reported \
    "$(echo "$out" | grep -qi 'conflict' && echo reported)"

echo "case: dirty worktree"
setup dirty
commit_on_feature feat.txt one
echo scribble > "$wt/uncommitted.txt"
before=$(git -C "$origin" rev-parse main)
out=$(run_land); rc=$?
check "nonzero exit" nonzero "$([ "$rc" -ne 0 ] && echo nonzero)"
check "origin main untouched" "$before" "$(git -C "$origin" rev-parse main)"
check "refusal mentions uncommitted work" refused \
    "$(echo "$out" | grep -qiE 'dirty|uncommitted|clean' && echo refused)"

# A second linked worktree on branch `other`, to be swept or spared. `idle`
# backdates its index past the sweep's one-hour cutoff.
add_other() {
    other="$root/$1/other"
    git -C "$clone" worktree add -q -b other "$other" main
}
idle() { touch -d '2 hours ago' "$clone/.git/worktrees/other/index"; }

echo "case: sweeps a spent, idle worktree"
setup sweep
add_other sweep
idle
commit_on_feature feat.txt one
out=$(run_land); rc=$?
check "exit 0" 0 "$rc"
check "spent worktree gone" gone "$([ -d "$other" ] || echo gone)"
check "its branch deleted" "" "$(git -C "$clone" branch --list other)"
check "says what it swept" said \
    "$(echo "$out" | grep -qi 'swept' && echo said)"
[ "$rc" -eq 0 ] || echo "$out" | sed 's/^/    /'

echo "case: leaves a busy worktree alone"
setup busy
add_other busy
# no idle: its index was just written, so an agent may be working in it
commit_on_feature feat.txt one
out=$(run_land)
check "busy worktree kept" here "$([ -d "$other" ] && echo here)"

echo "case: leaves unmerged work alone"
setup unmerged
add_other unmerged
printf 'x\n' > "$other/own.txt"
git -C "$other" add -A
git -C "$other" commit -qm "other: own work"
idle
commit_on_feature feat.txt one
out=$(run_land)
check "unmerged worktree kept" here "$([ -d "$other" ] && echo here)"
check "its commit survives" x "$(git -C "$clone" show other:own.txt 2>/dev/null)"

echo "case: leaves a dirty worktree alone"
setup dirtysweep
add_other dirtysweep
echo scribble > "$other/untracked.txt"
idle
commit_on_feature feat.txt one
out=$(run_land)
check "dirty worktree kept" here "$([ -d "$other" ] && echo here)"
check "untracked file survives" scribble "$(cat "$other/untracked.txt" 2>/dev/null)"

echo
if [ "$fails" -eq 0 ]; then
    echo "PASS: all land contract cases"
else
    echo "FAIL: $fails check(s) failed"
    exit 1
fi
