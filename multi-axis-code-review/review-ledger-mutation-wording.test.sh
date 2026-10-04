#!/usr/bin/env bash
# Guards #1270: both mutation calls into the review ledger. The correctness reviewer's
# witness check appends one `witness-mutation` / `call-site-mutation` row per mutation
# (stated in SKILL.md § 4 and carried by witness-check.sh itself), and the worker's own
# mutation check appends one `worker-mutation` row per mutation (implement/SKILL.md
# § Build). Goes red when either call, its refusal rule, or the agent pointer is dropped.
# Prose assertion only; review_ledger_mutation_test.py exercises the command and
# witness-check.test.sh runs the script, so the script's own lines are not matched here.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
worker="$here/../implement/SKILL.md"
agent="$here/../flow/claude/agents/diff-reviewer.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### 4. Spawn the three sub-agents in parallel' '### 5. Aggregate'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
for h in '### Build' '### Review'; do
  grep -qx "$h" "$worker" || { echo "FAIL: heading '$h' missing from implement/SKILL.md" >&2; exit 1; }
done
four="$(sed -n '/^### 4\. Spawn/,/^### 5\. Aggregate$/p' "$skill" | flatten)"
build="$(sed -n '/^### Build$/,/^### Review$/p' "$worker" | flatten)"
agent_text="$(flatten < "$agent")"
[ -n "$four" ] && [ -n "$build" ] && [ -n "$agent_text" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ 4" "$four" '**A witness check ends with one `append` per mutation**'
check_in "§ 4" "$four" 'review_ledger.py append --type witness-mutation'
check_in "§ 4" "$four" '`call-site-mutation` for an id passed with `--call-site`'
check_in "§ 4" "$four" 'An `unknown` stays `unknown`'
check_in "§ 4" "$four" 'the script exits 4'
check_in "diff-reviewer" "$agent_text" 'appends one mutation row per mutation too'
check_in "§ Build" "$build" 'review_ledger.py append --repo <repo> --ticket <n> --type worker-mutation --mutation-id <id> --outcome red|green|unknown --seconds <s>'
check_in "§ Build" "$build" 'A mutation that never reached its suite is `unknown`, never `red`'
check_in "§ Build" "$build" 'A refusal goes to the controller, never skipped'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
