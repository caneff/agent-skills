#!/usr/bin/env bash
# Guards #890: the frontier reader's fallback parses a *specification*, not
# whatever prose it meets, so the grammar has to be written down where both
# ends can read it — `burndown/references/frontier.md` for the reader, and
# `/to-tickets` for the writer that feeds it. On #781 eight of twenty-one
# `ready-for-agent` tickets carried no `## Blocked by` section at all; a
# writer that emits it only on trackers without native edges leaves that hole
# open, so to-tickets emits the section on every ticket and adds native edges
# where the tracker has them.
# This is a prose assertion over two SKILL/reference docs — there is no
# harness that runs a skill's own prose. The parser's behaviour is tested in
# burndown/frontier_test.py.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
grammar="$here/references/frontier.md"
skill="$here/SKILL.md"
to_tickets="$here/../to-tickets/SKILL.md"
tracker="$here/../docs/agents/issue-tracker.md"

for f in "$grammar" "$skill" "$to_tickets" "$tracker"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

flatten() { tr '\n' ' ' | tr -s ' '; }

grammar_text="$(flatten <"$grammar")"
skill_text="$(flatten <"$skill")"
# Scope the to-tickets needles to its publishing step, the way
# implement/closing-issue-wording.test.sh scopes each needle to its section —
# a phrase as generic as "in addition to" must not be satisfied by unrelated
# prose elsewhere in the file.
to_tickets_text="$(sed -n '/^### 5\. Publish the tickets/,/^<local-ticket-template>/p' "$to_tickets" | flatten)"
[ -n "$to_tickets_text" ] || { echo "FAIL: could not extract step 5 from to-tickets/SKILL.md" >&2; exit 1; }

tracker_text="$(flatten <"$tracker")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: the grammar doc states each of the three sources, in order, and
# names the native field that is the live gate.
check_in "$grammar_text" 'issue_dependencies_summary.blocked_by' references/frontier.md
check_in "$grammar_text" 'open blockers only' references/frontier.md

# Rule 2: the fallback's grammar is specified — the heading, the reference
# form, and the way to say there are none.
check_in "$grammar_text" '## Blocked by' references/frontier.md
check_in "$grammar_text" '#NNN' references/frontier.md
check_in "$grammar_text" 'None — can start immediately' references/frontier.md

# Rule 2b: all three written forms the tree uses are in the grammar, so a
# ticket written to any of the repo's own templates is not read as silence.
check_in "$grammar_text" 'Blocked by: #7, #8' references/frontier.md
check_in "$grammar_text" '`**Blocked by:** ...`' references/frontier.md

# Rule 3: silence is its own answer, and it is never read as unblocked.
check_in "$grammar_text" 'unresolved' references/frontier.md
check_in "$grammar_text" 'never dispatched' references/frontier.md

# Rule 4: the reader is reachable from the skill that owns it.
check_in "$skill_text" 'references/frontier.md' burndown/SKILL.md
check_in "$skill_text" 'frontier.py' burndown/SKILL.md

# Rule 5: /to-tickets writes what the reader parses — the section on every
# ticket, native edges as well where the tracker has them, in that grammar.
check_in "$to_tickets_text" '--add-blocked-by' to-tickets/SKILL.md
check_in "$to_tickets_text" 'in addition to' to-tickets/SKILL.md
check_in "$to_tickets_text" 'frontier.md' to-tickets/SKILL.md
check_in "$to_tickets_text" 'never omit' to-tickets/SKILL.md

# Rule 6: the standing tracker doc agrees with the grammar — the same three
# forms, and a frontier of three buckets rather than two. Before #890 its
# "Frontier query" dropped blocked tickets and dispatched everything else,
# so a ticket that stated nothing went to a worker.
check_in "$tracker_text" 'three forms the frontier reader parses' docs/agents/issue-tracker.md
check_in "$tracker_text" 'unresolved' docs/agents/issue-tracker.md
check_in "$tracker_text" 'Silence is unresolved, never unblocked' docs/agents/issue-tracker.md

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/blocked-by-grammar.test.sh"
else
  exit 1
fi
