#!/usr/bin/env bash
# Guards #1269: the wave's Codex pass (implement/SKILL.md § The Codex pass) writes one
# review-ledger row per pass through `review_ledger.py append`, reads usage with the gate's own
# reader before and after, and appends a skipped pass with its reason. Goes red when the
# instruction, the usage reads, the skip row or the unknown-not-zero rule is dropped. Prose
# assertion only; docs/research/review_ledger_codex_append_test.py exercises the command.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '#### The Codex pass' '### Before the PR'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
merge="$(sed -n '/^#### The Codex pass$/,/^### Before the PR$/p' "$skill" | flatten)"
[ -n "$merge" ] || { echo "FAIL: could not extract § The Codex pass" >&2; exit 1; }

fail=0
check_in() {
  case "$1" in *"$2"*) ;; *) echo "FAIL: implement/SKILL.md § The Codex pass is missing: $2" >&2; fail=1 ;; esac
}
check_in "$merge" '**Every pass is one ledger row** (#1269)'
check_in "$merge" 'usage_before=$(python3 ~/.agents/skills/implement/codex-usage-gate.py --percent)'
check_in "$merge" 'usage_after=$(python3 ~/.agents/skills/implement/codex-usage-gate.py --percent)'
check_in "$merge" '"usage_before": "%s", "usage_after": "%s"}'
check_in "$merge" 'review_ledger.py append --repo <repo> --ticket <n> --type codex-gate'
check_in "$merge" 'with `--refusal "<why>"` added'
check_in "$merge" 'append it with `--skip-reason "<the printed line>"` and no other flag'
check_in "$merge" 'append its ledger skip row (below), and name the skip in the PR body'
check_in "$merge" 'Append its ledger row with `--refusal "<why>"` (below)'
check_in "$merge" 'A usage reading that fails, on either side, is `unknown`, never zero'
check_in "$merge" 'A refusal from `append` itself goes to the controller in "PR up", never skipped'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
