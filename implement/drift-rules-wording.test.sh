#!/usr/bin/env bash
# Guards #1252: three rules against drift a PR creates, each stated once in
# implement/SKILL.md — reuse before writing (§ Build), the stale-reference
# check (§ Before the PR), and the blocking kinds (§ Review, beside the
# severity mapping and the reachability bar). multi-axis-code-review points
# at the blocking kinds rather than restating them, and its verification
# pass fails a blocking-kind finding left as `leftover`. Prose assertion over
# the two SKILL.md files; stale_refs_test.py exercises the script.
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
verify="$(sed -n '/^### 6\. The verification pass$/,/^## Why separate axes$/p' "$maxis" | flatten)"
maxis_text="$(flatten <"$maxis")"
for s in build review before spawn verify; do
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

# 3. The blocking kinds, beside the severity mapping and the reachability bar.
check_in "§ Review" "$review" '**The blocking kinds.**'
check_in "§ Review" "$review" 'added a second copy of existing code or data'
check_in "§ Review" "$review" 'left a doc, docstring, comment or alias claiming a state the PR changed'
check_in "§ Review" "$review" 'is fixed in this PR before merge'
check_in "§ Review" "$review" "The adjacent-fix rule's size limit does not apply"
check_in "§ Review" "$review" 'It is never `leftover`'
check_in "§ Review" "$review" 'never `filed` unless the fix needs its own design'
check_in "§ Review" "$review" 'plain `fixed` line, with no `scope`'
check_once SKILL.md "$whole" '**The blocking kinds.**'
check_in "§ Build" "$build" "§ Review's blocking kinds"
# The bar still comes first: an unreachable finding is disputed whatever its kind.
check_in "§ Review" "$review" 'applied after the reachability bar'
# § Review's text orders them: mapping, bar, blocking kinds, adjacent-fix rule.
order="$(grep -n -F -e '**The severity mapping.**' -e '**The reachability bar.**' \
  -e '**The blocking kinds.**' -e '**The adjacent-fix rule.**' "$skill" | cut -d: -f2- | sed 's/^ *//' | cut -c1-24 | tr '\n' '|')"
[ "$order" = '**The severity mapping.*|**The reachability bar.*|**The blocking kinds.** |**The adjacent-fix rule.|' ] ||
  { echo "FAIL: § Review's four rules are out of order: $order" >&2; fail=1; }

# Chris's ruling on PR #1263 (P1): the blocking kinds cover a Codex-pass
# finding at merge as well as a round-1 one, and each Codex disposition site
# points back at § Review instead of offering `leftover` unqualified.
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
grep -q '^## Someone else' "$skill" || { echo "FAIL: heading '## Someone else' missing" >&2; exit 1; }
check_in "§ Review" "$review" 'or of any Codex pass at merge'
check_in "§ The merge first pass" "$merge" "fixed in a commit (always, for one of § Review's blocking kinds)"
check_in "§ The merge second pass" "$merge" "or is one of § Review's blocking kinds, goes to the worker"
check_in "§ The merge third pass" "$merge" "except one of § Review's blocking kinds"
n="$(grep -o -F -- "§ Review's blocking kinds" <<<"$merge" | wc -l || true)"
[ "$n" -ge 3 ] || { echo "FAIL: § The merge points at the blocking kinds $n times, wanted all three passes" >&2; fail=1; }

# multi-axis-code-review points at the rule, and states neither kind itself.
check_in "multi-axis-code-review § 4" "$spawn" "\`implement/SKILL.md\` § Review's blocking kinds"
check_in "multi-axis-code-review § 4" "$spawn" '`blocking:`'
# The standing brief every reviewer reads carries the tag, not only the
# caller's prose (S1 on PR #1252's round 1).
reviewer="$(flatten <"$here/../flow/claude/agents/diff-reviewer.md")"
check_in "diff-reviewer.md" "$reviewer" "\`implement/SKILL.md\` § Review's blocking kinds"
check_in "diff-reviewer.md" "$reviewer" '`blocking:`'
check_in "§ Review" "$review" 'opening its sidecar `title` with `blocking:`'
check_in "§ Before the PR" "$before" 'Commit first'
check_in "multi-axis-code-review § 6" "$verify" 'on any of five things:'
check_in "multi-axis-code-review § 6" "$verify" "a finding of one of \`implement/SKILL.md\` § Review's blocking kinds"
for phrase in 'second copy of existing code or data' 'claiming a state the PR changed'; do
  case "$maxis_text" in *"$phrase"*)
    echo "FAIL: multi-axis-code-review restates the blocking kinds ('$phrase'); point at implement instead" >&2; fail=1 ;;
  esac
done
[ "$fail" -eq 0 ] && echo "PASS $0"
exit "$fail"
