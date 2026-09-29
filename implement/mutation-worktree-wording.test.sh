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
has "§ Build" "$build" "the *Isolation* paragraph of \`multi-axis-code-review/SKILL.md\`'s witness-check block"
lacks "§ Build" "$build" 'then restore it'
has "§ The PR" "$pr" 'the throwaway worktree the mutation ran in'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
