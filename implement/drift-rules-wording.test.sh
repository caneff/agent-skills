#!/usr/bin/env bash
# Guards #1252, as #1401 left it: two rules against drift a PR creates, each
# stated once in implement/SKILL.md — reuse before writing (§ Build) and the
# stale-reference check (§ Before the PR). The third, the "blocking kinds"
# (a second copy, a stale claim) that were fixed in the PR while other
# findings could be left over, went with the leftover outcome: § Review now
# fixes every valid finding, so a kind that decides fix-versus-leftover has
# nothing to decide, and the test asserts the tag is gone from the three files
# that carried it. Prose assertion; stale_refs_test.py exercises the script.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
maxis="$here/../multi-axis-code-review/SKILL.md"
flatten() { tr '\n' ' ' | tr -s ' '; }

# A sed range whose end heading was renamed runs to EOF and would widen the
# slice; require each end heading so a rename fails here, not silently.
for h in '### Review' '### Before the PR' '### The PR'; do
  grep -qx "$h" "$skill" || { echo "FAIL: heading '$h' missing from SKILL.md" >&2; exit 1; }
done
for h in '### 5. Aggregate' '## Why separate axes'; do
  grep -qx "$h" "$maxis" || { echo "FAIL: heading '$h' missing from multi-axis-code-review/SKILL.md" >&2; exit 1; }
done
build="$(sed -n '/^### Build$/,/^### Review$/p' "$skill" | flatten)"
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
before="$(sed -n '/^### Before the PR$/,/^### The PR$/p' "$skill" | flatten)"
whole="$(flatten <"$skill")"
spawn="$(sed -n '/^### 4\. Spawn the three sub-agents in parallel$/,/^### 5\. Aggregate$/p' "$maxis" | flatten)"
maxis_text="$(flatten <"$maxis")"
for s in build review before spawn; do
  [ -n "${!s}" ] || { echo "FAIL: could not extract section '$s'" >&2; exit 1; }
done

fail=0
check_in() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
check_once() { # <haystack name> <haystack> <phrase>
  local n
  n="$(grep -o -F -- "$3" <<<"$2" | wc -l || true)"
  [ "$n" -eq 1 ] || { echo "FAIL: expected '$3' exactly once in $1, found $n" >&2; fail=1; }
}

# 1. Reuse before writing.
check_in "§ Build" "$build" '**Reuse before writing.**'
check_in "§ Build" "$build" 'a helper, constant, loader or data file'
check_in "§ Build" "$build" 'search the repo for an existing one and reuse it'
check_once SKILL.md "$whole" '**Reuse before writing.**'

# 2. The stale-reference check.
check_in "§ Before the PR" "$before" '**Then find the stale references**'
check_in "§ Before the PR" "$before" 'python3 ~/.agents/skills/implement/stale_refs.py'
check_in "§ Before the PR" "$before" 'git diff origin/<default>...HEAD'
check_in "§ Before the PR" "$before" 'renamed or deleted'
check_in "§ Before the PR" "$before" 'top-level name it removed or renamed'
check_in "§ Before the PR" "$before" 'Exit 2 is not a clean tree'
check_once SKILL.md "$whole" 'stale_refs.py'

# 3. The blocking kinds are retired: every valid finding is fixed in the PR.
reviewer="$(flatten <"$here/../flow/claude/agents/diff-reviewer.md")"
for pair in "implement/SKILL.md:$whole" "multi-axis-code-review/SKILL.md:$maxis_text" "diff-reviewer.md:$reviewer"; do
  case "${pair#*:}" in
    *"blocking kinds"*|*'`blocking:`'*)
      echo "FAIL: ${pair%%:*} still names the blocking kinds, which #1401 retired" >&2; fail=1 ;;
  esac
done
check_in "§ Review" "$review" 'a valid finding is fixed in the PR the review covers'
check_in "§ Before the PR" "$before" 'Commit first'
[ "$fail" -eq 0 ] && echo "PASS $0"
