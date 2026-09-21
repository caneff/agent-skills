#!/usr/bin/env bash
# Guards #871: /file-ticket hands the `gh issue create` command back on a
# repo whose origin owner isn't the caller's gh login, so a worker there has
# no ticket number to record. implement/SKILL.md § Review must name that
# fourth disposition (`handed back`), carry it in the PR body list and the
# dispositions sidecar, and § Someone else's repo must send the command to
# the controller. Prose assertion over SKILL.md; no harness runs the prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
pr="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
else_repo="$(sed -n '/^## Someone else/,$p' "$skill" | flatten)"
[ -n "$review" ] && [ -n "$pr" ] && [ -n "$else_repo" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ Review" "$review" 'handed back: <the gh issue create command>'
check_in "§ Review sidecar" "$review" '"outcome": "handed-back", "command"'
check_in "§ The PR" "$pr" 'handed back, with the command'
check_in "§ Someone else's repo" "$else_repo" 'handed-back finding'
exit "$fail"
