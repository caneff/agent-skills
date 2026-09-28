#!/usr/bin/env bash
# Guards #1188: § The merge step 2 blocks a heavy PR whose dispositions
# sidecar is missing or empty, and § Before the PR step 5 says the gate
# refuses it. Prose assertion over implement/SKILL.md.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }
fail=0
check_in() { # <section text> <label> <needle>
  case "$1" in *"$3"*) ;; *) echo "FAIL: $2 is missing: $3" >&2; fail=1 ;; esac
}
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
before="$(sed -n '/^### Before the PR$/,/^### The PR$/p' "$skill" | flatten)"
[ -n "$merge" ] && [ -n "$before" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

check_in "$merge" "§ The merge" 'carries its verification pass'
check_in "$merge" "§ The merge" 'a heavy Claude-lane PR with no verification pass (#1188)'
check_in "$merge" "§ The merge" 'bash ~/.agents/skills/implement/verification-check.sh <n>'
check_in "$merge" "§ The merge" 'or the merge waits and the worker is sent back to § Review step 2'
check_in "$merge" "§ The merge" 'A Codex-lane PR is exempt'
check_in "$before" "§ Before the PR" 'when `dispositions-<n>.jsonl` is missing or empty (#1188)'
check_in "$before" "§ Before the PR" 'A round 1 that found nothing'
check_in "$before" "§ Before the PR" 'PRE_REPORT_NO_VERIFICATION="<why>"'
check_in "$(flatten <"$here/codex-lane.md")" "codex-lane.md" 'PRE_REPORT_NO_VERIFICATION="codex lane: no Claude axes"'
[ "$fail" = 0 ] && echo "ALL PASS" || exit 1
