#!/usr/bin/env bash
# Guards #895: what stops a clump, what reaches Chris, and what a controller
# must have checked before it rules instead. Three park causes and no fourth
# — every other blocker is a controller ruling, and a fourth cause added
# quietly is how "the controller decides" erodes into "the controller asks".
# Two docs: `burndown/SKILL.md` for the run's own policy, and `CONTEXT.md`'s
# Controller entry, which is the escalation list every controller reads.
# Prose assertions no Python harness can make.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reference="$here/references/parking.md"
context="$here/../CONTEXT.md"

for f in "$skill" "$reference" "$context"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# Each section scoped to itself, so a needle this generic is never satisfied
# by prose elsewhere in the skill. Each runs to the next `## `.
section_of() {
  sed -n "/^##[[:space:]]*$1[[:space:]]*\$/,/^##[[:space:]]/{/^##[[:space:]]*$1[[:space:]]*\$/d; /^##[[:space:]][^#]/d; p}" "$skill"
}
parking="$(section_of 'Parking and escalation')"
ruling="$(section_of 'Before a controller rules')"
[ -n "$parking" ] || { echo "FAIL: burndown/SKILL.md has no § Parking and escalation" >&2; exit 1; }
[ -n "$ruling" ] || { echo "FAIL: burndown/SKILL.md has no § Before a controller rules" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }
parking_text="$(printf '%s\n' "$parking" | flatten)"
ruling_text="$(printf '%s\n' "$ruling" | flatten)"
reference_text="$(flatten <"$reference")"
# The Controller entry alone — the list a controller reads — and not the rest
# of the glossary, which names controllers throughout.
controller_text="$(sed -n '/^\*\*Controller\*\*:/,/^_Avoid_:/p' "$context" | flatten)"
[ -n "$controller_text" ] || { echo "FAIL: CONTEXT.md has no Controller entry" >&2; exit 1; }

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: exactly three park causes, each named, and everything else stated as
# a controller ruling. The count is the assertion a needle cannot make: a
# fourth numbered cause fails here even if it reads plausibly.
causes="$(printf '%s\n' "$parking" | grep -cE '^[0-9]+\. ' || true)"
if [ "$causes" -ne 3 ]; then
  echo "FAIL: § Parking and escalation lists $causes park causes, not 3" >&2
  fail=1
fi
check_in "$parking_text" 'and no others' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'only **Chris** can answer' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'harness refuses' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'CLEAN' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'controller ruling' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'ready-for-human' 'burndown/SKILL.md § Parking and escalation'

# Rule 2: a parked clump keeps its workspace and holds its closure off the
# frontier, and two consecutive parks with no landing stop the run.
check_in "$parking_text" 'keeps its workspace' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'out of the frontier' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'Two consecutive parks' 'burndown/SKILL.md § Parking and escalation'

# Rule 3: the bounded probe is stated as something a controller may commission
# before escalating.
check_in "$parking_text" 'bounded probe' 'burndown/SKILL.md § Parking and escalation'
check_in "$parking_text" 'before it escalates' 'burndown/SKILL.md § Parking and escalation'

# Rule 4: the three ruling clauses, each with the trap it closes.
check_in "$ruling_text" 'the thing that ships' 'burndown/SKILL.md § Before a controller rules'
check_in "$ruling_text" "tool's source" 'burndown/SKILL.md § Before a controller rules'
check_in "$ruling_text" 'not its help text' 'burndown/SKILL.md § Before a controller rules'
check_in "$ruling_text" 'Codex finding' 'burndown/SKILL.md § Before a controller rules'
check_in "$ruling_text" 'not a courier' 'burndown/SKILL.md § Before a controller rules'
clauses="$(printf '%s\n' "$ruling" | grep -cE '^[0-9]+\. ' || true)"
if [ "$clauses" -ne 3 ]; then
  echo "FAIL: § Before a controller rules lists $clauses clauses, not 3" >&2
  fail=1
fi

# Rule 5: CONTEXT.md's Controller entry carries both new escalation shapes,
# since that entry — not this skill — is what every controller reads.
check_in "$controller_text" 'the spec is silent' CONTEXT.md
check_in "$controller_text" 'a lane-mandated step the harness refuses' CONTEXT.md

# Rule 6: the reference carries the evidence each clause came from, so the
# next reader can weigh it rather than only obey it.
check_in "$parking_text" 'references/parking.md' 'burndown/SKILL.md § Parking and escalation'
for needle in '#367' '#351' '#559' '#781'; do
  check_in "$reference_text" "$needle" references/parking.md
done

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/parking.test.sh"
else
  exit 1
fi
