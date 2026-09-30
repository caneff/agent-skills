#!/usr/bin/env bash
# Guards #1269: the controller's Codex pass (implement/SKILL.md § The merge step 3) writes one
# review-ledger row per pass through `review_ledger.py append`, reads usage with the gate's own
# reader before and after, and appends a skipped pass with its reason. Goes red when the
# instruction, the usage reads, the skip row or the unknown-not-zero rule is dropped. Prose
# assertion only; docs/research/review_ledger_codex_append_test.py exercises the command.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### The merge' '## Someone else'"'"'s repo'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
[ -n "$merge" ] || { echo "FAIL: could not extract § The merge" >&2; exit 1; }

fail=0
check_in() {
  case "$1" in *"$2"*) ;; *) echo "FAIL: implement/SKILL.md § The merge is missing: $2" >&2; fail=1 ;; esac
}
check_in "$merge" '**Every pass is one ledger row** (#1269)'
check_in "$merge" 'before=$(python3 ~/.agents/skills/implement/codex-usage-gate.py --percent)'
check_in "$merge" 'review_ledger.py append --repo <repo> --ticket <n> --type codex-$phase --usage-before "$before"'
check_in "$merge" 'review_ledger.py append --repo <repo> --ticket <n> --type codex-<phase> --skip-reason "<the printed line>"'
check_in "$merge" 'A usage reading that fails, on either side, is `unknown`, never zero'
check_in "$merge" 'A refusal from `append` itself goes to the controller, never skipped'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
