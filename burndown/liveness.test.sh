#!/usr/bin/env bash
# Guards #894: how a controller knows its workers are alive is written down in
# `burndown/SKILL.md` § Liveness, ranked — the wake first, the stop alert
# demoted to a hint, the bounded sweep as the backstop — and a worker's
# declared core count is the bridge between a budget in slots and a box whose
# contention is in cores. Prose assertions no Python harness can make; the
# sweep's and the hold's behaviour are tested in burndown/loop_test.py.
# The load-bearing one is negative: across the two #781 runs the stop alert
# fired six times and was wrong six times, so no instruction anywhere in this
# skill may tell a controller to park, hold or wait on that alert alone.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reference="$here/references/liveness.md"

for f in "$skill" "$reference"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# Scoped to `## Liveness` and its subsections, so a needle this generic is
# never satisfied by prose elsewhere in the skill. Runs to the next `## `.
section="$(sed -n '/^##[[:space:]]*Liveness[[:space:]]*$/,/^##[[:space:]]/{/^##[[:space:]]*Liveness[[:space:]]*$/d; /^##[[:space:]][^#]/d; p}' "$skill")"
[ -n "$section" ] || { echo "FAIL: burndown/SKILL.md has no § Liveness" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }
liveness_text="$(printf '%s\n' "$section" | flatten)"
reference_text="$(flatten <"$reference")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: the wake is the primary path, and it is a worker's own send.
check_in "$liveness_text" 'primary' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'SendMessage' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" '#778' 'burndown/SKILL.md § Liveness'

# Rule 2: the stop alert is a hint — "read this pane" — with the measurement
# that demoted it.
check_in "$liveness_text" 'hint' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'read this pane' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'six times' 'burndown/SKILL.md § Liveness'

# Rule 3: the sweep is bounded, idle-wake only, and neither a timer nor a
# blocking call — a controller inside a tool call hears no worker at all.
check_in "$liveness_text" 'bounded' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'never a timer' 'burndown/SKILL.md § Liveness'
# One deadline for the whole sweep: a per-probe bound composes into N times
# the wait, which is the same deafness by another route.
check_in "$liveness_text" 'one deadline for the whole sweep' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'unswept' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'blocking' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'nothing else to do' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'burndown/loop.py sweep' 'burndown/SKILL.md § Liveness'

# Rule 4: a vanished pane is a verdict of its own, and the sweep's own blind
# spot is stated rather than left for a controller to over-read (#925).
check_in "$liveness_text" 'vanished' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" '#925' 'burndown/SKILL.md § Liveness'

# Rule 5: a worker declares its parallel job's core count, and the controller
# holds the free slots against it and says so.
check_in "$liveness_text" 'core count' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'runfile.py job' 'burndown/SKILL.md § Liveness'
# The declaration is state on the clump, not an argument to one dispatch: a
# hold that lives in argv is a hold a resumed controller cannot recover.
check_in "$liveness_text" 'never from its own argv' 'burndown/SKILL.md § Liveness'
check_in "$liveness_text" 'status line' 'burndown/SKILL.md § Liveness'
# A worker that launched no parallel job says so: silence read as zero is a
# worker that forgot, charged as a worker that ran nothing.
check_in "$liveness_text" 'silence is not zero' 'burndown/SKILL.md § Liveness'

# Rule 6: the reference carries the evidence, so the next reader can weigh the
# demotion rather than only obey it.
check_in "$liveness_text" 'references/liveness.md' 'burndown/SKILL.md § Liveness'
check_in "$reference_text" '#781' references/liveness.md
check_in "$reference_text" 'six' references/liveness.md
check_in "$reference_text" '25.8' references/liveness.md
check_in "$reference_text" '#925' references/liveness.md

# Rule 7, the load-bearing one: nowhere in the skill does the alert on its own
# carry an instruction to park, hold or wait. Every sentence naming it is read,
# and one that also reaches for a park must carry `never` — the prohibition
# itself, not merely some negation somewhere in the sentence. "If the stop
# alert fires and **no** reply has arrived, hold the slot" is an instruction to
# hold on the alert alone, and a filter that exempted `no ` passed it.
offenders="$(tr '\n' ' ' <"$skill" | sed 's/\([.!?]\) /\1\n/g' |
  grep -iE 'stop alert|stop hook|worker-stop-alert' |
  grep -iE 'park|stall|stuck|hold|wait' |
  grep -vi 'never') " || true
if [ -n "${offenders//[[:space:]]/}" ]; then
  echo "FAIL: burndown/SKILL.md parks on the stop alert alone:" >&2
  echo "$offenders" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/liveness.test.sh"
else
  exit 1
fi
