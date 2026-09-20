#!/usr/bin/env bash
# Guards #897: `implement-spec` is policy over `burndown/SKILL.md` § The loop
# with four overrides — the nesting, the exploration pass's contradiction
# check, the closing ticket, and the spec-level review — and it restates none
# of that loop. Prose assertions no Python harness can make; the two readers'
# behaviour is tested in implement-spec/contradictions_test.py and
# implement-spec/closing_ticket_test.py.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
exploration="$here/references/exploration.md"
closing="$here/references/closing-ticket.md"
handoff="$here/../burndown/references/spec-handoff.md"

for f in "$skill" "$exploration" "$closing" "$handoff"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

flatten() { tr '\n' ' ' | tr -s ' '; }
skill_text="$(flatten <"$skill")"
exploration_text="$(flatten <"$exploration")"
closing_text="$(flatten <"$closing")"
handoff_text="$(flatten <"$handoff")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}
# Word-bounded, so that a needle like `hub` is not satisfied by the `github.com`
# in a link — a not-in check that fires on a substring of an unrelated word
# fails the file for prose it never contains.
check_not_in() {
  local haystack="$1" needle="$2" where="$3"
  if printf '%s' "$haystack" |
       grep -qE "(^|[^[:alnum:]./-])$needle([^[:alnum:]-]|$)"; then
    echo "FAIL: $where must not contain: $needle" >&2
    fail=1
  fi
}

# Rule 1: the loop is pointed at, by name, and lives in the other skill.
check_in "$skill_text" 'burndown/SKILL.md' implement-spec/SKILL.md
check_in "$skill_text" '§ The loop' implement-spec/SKILL.md

# Rule 2: and none of it is restated here. Each needle below is a rule that
# lives in § The loop; repeating one is the drift #779 named.
for needle in 'continuous' 'no waves' 'one hop' 'hub' 'free -g' 'uptime' \
              'frozen' 'declared None' 'runfile.py clump'; do
  check_not_in "$skill_text" "$needle" 'implement-spec/SKILL.md § the loop pointer'
done
# Nor another lane's command grammar — naming one bare, with a pointer, is
# the point.
if echo "$skill_text" | grep -qE '(implement-dispatch|merge-cleanup|herdr [a-z]+)[^.,)`]*[ `](--|<)'; then
  echo "FAIL: implement-spec/SKILL.md restates another lane's grammar:" >&2
  echo "$skill_text" | grep -oE '(implement-dispatch|merge-cleanup|herdr [a-z]+)[^.,)`]*[ `](--|<)[^ ]*' >&2
  fail=1
fi

# Rule 3: the nesting — worker to the burn that dispatched it, controller to
# its own slices, and its slots debited from that burn rather than added to
# the box's load.
check_in "$skill_text" 'worker to the burn' implement-spec/SKILL.md
check_in "$skill_text" 'controller to its own slices' implement-spec/SKILL.md
check_in "$skill_text" 'debited from' implement-spec/SKILL.md

# Rule 4: the contradiction check reads the spec's own ticket list first, and
# only one of its verdicts reaches Chris.
check_in "$skill_text" "spec's own ticket list" implement-spec/SKILL.md
check_in "$skill_text" 'not yet built' implement-spec/SKILL.md
check_in "$skill_text" 'summary line' implement-spec/SKILL.md
check_in "$skill_text" 'differently' implement-spec/SKILL.md
check_in "$skill_text" 'contradictions.py' implement-spec/SKILL.md

# Rule 5: the closing ticket names the seam and its blind spot, and a surface
# the seam cannot reach buys one open of the real thing.
check_in "$skill_text" 'blind' implement-spec/SKILL.md
check_in "$skill_text" 'open of the real thing' implement-spec/SKILL.md
check_in "$skill_text" 'closing_ticket.py' implement-spec/SKILL.md

# Rule 6: the spec-level review is handed shas, and the reason a range is
# wrong is stated where the reader decides.
check_in "$skill_text" 'list of merge shas' implement-spec/SKILL.md
# `run file` alone is satisfied by the loop-pointer paragraph above, which
# names the frontier and the run file in passing; the needle has to be the
# spec-level review's own sentence.
check_in "$skill_text" 'read off the run file' implement-spec/SKILL.md
check_in "$skill_text" 'never a git range' implement-spec/SKILL.md

# Rule 7: both references are reachable from the skill and carry the evidence
# their rules came from, so the next reader can weigh them.
check_in "$skill_text" 'references/exploration.md' implement-spec/SKILL.md
check_in "$skill_text" 'references/closing-ticket.md' implement-spec/SKILL.md
check_in "$exploration_text" '#781' implement-spec/references/exploration.md
check_in "$exploration_text" '#367' implement-spec/references/exploration.md
# The line between the two verdicts that carry the rule, and the tiebreak —
# without it the pass reads the #781 decisions either way (C1).
check_in "$exploration_text" 'begins' implement-spec/references/exploration.md
check_in "$exploration_text" 'tiebreak' implement-spec/references/exploration.md
check_in "$closing_text" '#781' implement-spec/references/closing-ticket.md
check_in "$closing_text" 'End-to-end seam' implement-spec/references/closing-ticket.md
check_in "$closing_text" 'Blind to' implement-spec/references/closing-ticket.md

# Rule 8: the handoff is a pointer — it says when a burn hands a spec over and
# where the policy lives, and states none of that policy itself.
check_in "$handoff_text" 'implement-spec' burndown/references/spec-handoff.md
# When to read it at all — `spec` alone is tautological in a file about specs.
check_in "$handoff_text" 'parent issue carries the `spec` label' burndown/references/spec-handoff.md
for needle in 'contradiction' 'blind spot' 'merge shas'; do
  check_not_in "$handoff_text" "$needle" burndown/references/spec-handoff.md
done

if [ "$fail" -eq 0 ]; then
  echo "PASS implement-spec/nested-run.test.sh"
else
  exit 1
fi
