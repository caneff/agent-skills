#!/usr/bin/env bash
# Guards #1261: a worker's mutation check runs in a throwaway detached worktree
# under .scratch/, after the work is committed, and nothing is restored in the
# live checkout — a `git checkout -- <file>` / `git restore` / `git stash` restore
# takes any uncommitted edit in that file with the mutation. § Build must say so,
# point at the review side's isolation recipe rather than copy it, and the
# "PR up" Mutation check line must name the worktree.
# Prose assertion over SKILL.md; no harness runs the prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### Build' '### Review' '### The PR' '### The merge'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
build="$(sed -n '/^### Build$/,/^### Review$/p' "$skill" | flatten)"
pr="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
[ -n "$build" ] && [ -n "$pr" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
has() { case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac; }
lacks() { case "$2" in *"$3"*) echo "FAIL: $1 still says: $3" >&2; fail=1 ;; esac; }

has "§ Build" "$build" 'Commit the work first'
has "§ Build" "$build" 'git worktree add --detach .scratch/'
has "§ Build" "$build" 'git worktree remove --force'
has "§ Build" "$build" 'Nothing is restored in the live checkout'
has "§ Build" "$build" "follow the *Isolation* paragraph of \`multi-axis-code-review/SKILL.md\`'s witness check"
# #1273 S3/OE1/OE2: the pointer is one clause, with no authoring aside.
lacks "§ Build" "$build" 'not a heading, so no section sign'
lacks "§ Build" "$build" 'a fenced recipe'
# #1273 P3: the one departure from the review recipe says why.
has "§ Build" "$build" "not the review recipe's path outside the checkout, because this workspace is yours"
# #1273 C3: a tree an earlier run left behind is cleared before the add, and
# the worktree is removed whatever the mutation's outcome.
has "§ Build" "$build" 'git worktree remove --force .scratch/mutation-<id> 2>/dev/null git worktree add --detach .scratch/mutation-<id> HEAD'
has "§ Build" "$build" 'whether it went red or not'
# r1-P1/r1-C2: the pre-clear cannot remove a directory git does not know, so
# a refused add stops the mutation rather than falling through to a stale tree.
has "§ Build" "$build" 'If the add still refuses, stop'
# r1-S1: the rule cites #1219 without claiming its tracker state.
lacks "§ Build" "$build" '#1219 is open'
# #1273 C2: the fresh tree lacks untracked and ignored setup, and the red
# message must be the stripped assertion (defect class 3, #1219).
has "§ Build" "$build" 'The worktree holds only tracked files'
has "§ Build" "$build" '#1219'
has "§ Build" "$build" 'it must be your stripped assertion, not a missing file or a denied path'
lacks "§ Build" "$build" 'then restore it'
# The only place Build may name a restore command is the sentence that forbids
# it; a reworded instruction elsewhere ("put the file back with git checkout")
# is the regression.
rest="${build/Nothing is restored in the live checkout:*(#1261)/}"
[ "$rest" != "$build" ] || { echo "FAIL: the prohibition sentence was not found in § Build" >&2; exit 1; }
for cmd in 'git checkout --' 'git restore' 'git stash' 'restore it' 'put the file back'; do
  lacks "§ Build outside its prohibition" "$rest" "$cmd"
done
# Each copy on its own: the template line and the report bullet both carry the
# phrase, so a whole-section search passes with either one reverted.
line="${pr#*Mutation check: <}"; line="${line%%Parallel jobs:*}"
[ "$line" != "$pr" ] || { echo "FAIL: Mutation check template line not found in § The PR" >&2; exit 1; }
has "Mutation check line" "$line" 'the throwaway worktree the mutation ran in'
bullet="${pr#*A mutation check\*\*, when}"; bullet="${bullet%%Add \"Chris merges\"*}"
[ "$bullet" != "$pr" ] || { echo "FAIL: mutation-check bullet not found in § The PR" >&2; exit 1; }
has "mutation-check bullet" "$bullet" 'the throwaway worktree the mutation ran in'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
