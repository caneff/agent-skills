#!/usr/bin/env bash
# Guards #1268: every review ends with `review_ledger.py append`, stated once in
# SKILL.md § 4 and pointed at from the diff-reviewer definition. Goes red
# when the instruction, its refusal rule, or either pointer is dropped. Prose
# assertion only; review_ledger_append_test.py exercises the command itself.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
agent="$here/../flow/claude/agents/diff-reviewer.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

for h in '### 4. Spawn the three sub-agents in parallel' '### 5. Aggregate' '## Why separate axes'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
four="$(sed -n '/^### 4\. Spawn/,/^### 5\. Aggregate$/p' "$skill" | flatten)"
agent_text="$(flatten < "$agent")"
[ -n "$four" ] && [ -n "$agent_text" ] || { echo "FAIL: could not extract sections" >&2; exit 1; }

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_in "§ 4" "$four" '**Every review ends with `append`**'
check_in "§ 4" "$four" 'review_ledger.py append --repo <repo> --ticket <n> --type <axis>'
check_in "§ 4" "$four" 'exits non-zero, naming what is missing'
check_in "§ 4" "$four" 'A refusal is reported, never skipped'
check_in "§ 4" "$four" 'the caller repeats it in its own report'
check_in "§ 4" "$four" 'review_ledger.py harvest'
check_in "diff-reviewer" "$agent_text" 'run `review_ledger.py append` as your last step'
check_in "diff-reviewer" "$agent_text" 'A refusal is the first line of your summary, never skipped'
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
