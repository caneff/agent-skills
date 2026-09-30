#!/usr/bin/env bash
# Guards #1208: the four gaps the #688 pilot (#1178, PR #1207) found in
# implement/codex-lane.md. Each is a rule a worker would otherwise infer from
# the lane's spirit:
#   1. Codex's own usage cap: stop and hand the owner the choice; never retry
#      and never pick a substitute review.
#   2. Codex's sandbox holds .git read-only: the worker commits Codex's diff as
#      plumbing, and the PR body says so.
#   3. No merge-time Codex pass on a Codex-lane PR (SKILL.md § The merge step 3
#      is Claude-lane only).
#   4. A ruling by the owner in a ticket comment is an opt-in.
# This is a prose assertion over the doc, not a behavioral test — there is no
# harness that runs the skills' own prose. Each check is scoped to the section
# that owns the rule, so the phrase pasted elsewhere does not satisfy it.
# Resolving via BASH_SOURCE sidesteps a leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lane="$here/codex-lane.md"

flatten() { tr '\n' ' ' | tr -s ' '; }
section() { # section <heading regex>: from that heading to the next `## `
  awk -v pat="$1" '
    $0 ~ "^## " { on = ($0 ~ pat) }
    on { print }
  ' "$lane" | flatten
}

optin="$(awk '/^## / { exit } { print }' "$lane" | flatten)"
build="$(section '^## The build$')"
reviews="$(section '^## The reviews$')"
cap="$(section "^## When Codex's own quota runs out$")"
guard() { # guard <section name> <extracted text>
  [ -n "$2" ] || { echo "FAIL: could not extract § $1 from its doc" >&2; exit 1; }
}
entry="$(awk '/^\*\*Codex builds this one\?\*\*/ { on = 1 } on && /^$/ { exit } on { print }' "$here/SKILL.md" | flatten)"
guard "opt-in" "$optin"
guard "The build" "$build"
guard "The reviews" "$reviews"
guard "Codex's own quota" "$cap"
guard "SKILL.md Codex routing" "$entry"

fail=0
check_in() {
  case "$1" in
    *"$2"*) ;;
    *) echo "FAIL: $3 is missing: $2" >&2; fail=1 ;;
  esac
}

# Gap 4: the ticket-comment opt-in, owner's own word only, in the lane doc and
# in the entry point a worker reads first.
check_in "$entry" 'a ruling by the owner in a ticket comment' 'SKILL.md routing paragraph'
check_in "$optin" 'a ruling by the owner in a ticket comment' 'opt-in'
check_in "$optin" "Another author's comment never opts a build in" 'opt-in'

# Gap 2: who commits when the sandbox cannot.
check_in "$build" "Codex's sandbox holds \`.git\` read-only" '§ The build'
check_in "$build" "commits Codex's diff as plumbing" '§ The build'
check_in "$build" 'authors none of it' '§ The build'
check_in "$build" 'The PR body says the commit was made by the worker and the diff was written by Codex' '§ The build'

# Gap 3: the relationship to the controller's merge-time gate.
check_in "$reviews" 'A Codex-lane PR gets no merge-time Codex pass' '§ The reviews'
check_in "$reviews" '`implement/SKILL.md` § The merge step 3' '§ The reviews'
check_in "$reviews" 'the lane'"'"'s own `/codex:adversarial-review` is its adversarial pass' '§ The reviews'

# Gap 1: Codex's own cap.
check_in "$cap" 'usage limit' "§ When Codex's own quota runs out"
check_in "$cap" 'Stop. Do not retry, and do not substitute a review' "§ When Codex's own quota runs out"
check_in "$cap" 'hand the owner the choice' "§ When Codex's own quota runs out"
check_in "$cap" 'a Claude review the owner rules as a one-off substitute' "§ When Codex's own quota runs out"
check_in "$cap" 'the PR body names the substitution' "§ When Codex's own quota runs out"

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-lane-gaps.test.sh"
else
  exit 1
fi
