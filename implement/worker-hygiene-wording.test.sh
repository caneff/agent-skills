#!/usr/bin/env bash
# Guards #909 (worker commit identity and file paths), #963 (the "PR up"
# controller trailer) and #951 (the lane's prose on codex-companion's inert
# --background). A prose assertion over implement/SKILL.md, not a behavioral
# test — there is no harness that runs the skill's own prose.
# Resolving via BASH_SOURCE sidesteps a caller's leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flat="$(tr '\n' ' ' <"$skill" | tr -s ' ')"

fail=0
check() {
  case "$flat" in
    *"$1"*) ;;
    *) echo "FAIL: implement/SKILL.md is missing: $1" >&2; fail=1 ;;
  esac
}

# #909: identity
check 'Commit identity comes from the repo'"'"'s config.'
check 'Never pass `-c user.email` or `-c user.name` to `git commit`'
check 'GitHub'"'"'s email-privacy rule rejected every push'
# #909: paths
check 'A file whose contents become public lives under your own workspace'"'"'s `.scratch/`'
check 'every `--body-file` for `gh pr create` and `gh pr edit`'
check 'never `/tmp`, never a shared scratchpad path'
check 'PR 908 went up carrying #886'"'"'s body'

# #963: trailer is in the template and explained
pr_section="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill")"
template="$(printf '%s\n' "$pr_section" | sed -n '/^PR up:/,/^```$/p')"
case "$template" in
  *'Controller: you dispatched me; merge this PR per implement/SKILL.md § The'*'merge-cleanup --repo <primary checkout> implement-<n>'*) ;;
  *) echo "FAIL: 'PR up:' template lacks the controller trailer" >&2; fail=1 ;;
esac
check 'the first line stays `PR up: <pr url>` as the preview'
check 'the first entry of `git worktree list`'
check 'the trailer reads "Chris merges" instead of the merge instruction'
check 'Your "PR up" message ends with the controller trailer'

# #951: the lane says --background is inert on this path
check '`--background` is parsed by `codex-companion.mjs` and never read on this path'

if [ "$fail" -eq 0 ]; then echo "PASS implement/worker-hygiene-wording.test.sh"; else exit 1; fi
