#!/usr/bin/env bash
# Guards #1030's prose: the sweep ticket's shape — title, label, blocked-by,
# the two filing moments, and the run report's three counts — lives only in
# `burndown/SKILL.md` § The sweep. A reader nothing states this in is a
# controller that files the sweep however it feels like that day, which is
# the one-ticket-per-finding sprawl #1024 exists to stop.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point that at the caller's repo (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

[ -f "$skill" ] || { echo "FAIL: missing $skill" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }

# Scoped to § The sweep, the same way tier-tagging.test.sh scopes to its own
# section: the rules have to be stated *in the section that owns them*, not
# anywhere the words happen to appear. The end address matches the next
# heading, whatever it is named — a literal "The frontier" end address fails
# open the moment a later heading is renamed or a section is appended after
# this one, and the range then runs to EOF and reads unrelated prose as if it
# were inside § The sweep (#1030 round-1 finding C1).
sweep_text="$(sed -n '/^#\{1,6\}[[:space:]]*The sweep/,/^#\{1,6\}[[:space:]]*[A-Z]/p' "$skill" | flatten)"
[ -n "$sweep_text" ] || { echo "FAIL: burndown/SKILL.md has no The sweep section" >&2; exit 1; }

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# The sweep ticket's own shape: title, label, blocked-by.
check_in "$sweep_text" 'Sweep: leftovers from burn' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'ready-for-agent' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'None — can start immediately.' 'burndown/SKILL.md § The sweep'

# The two filing moments.
check_in "$sweep_text" 'run close' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'stops on two parks' 'burndown/SKILL.md § The sweep'

# Zero leftovers files nothing, and the report says so.
check_in "$sweep_text" 'zero' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'files nothing' 'burndown/SKILL.md § The sweep'

# The renderer and the counter this section invokes, so a controller reaches
# the commands and not just a description of them.
check_in "$sweep_text" 'burndown/sweep.py render <run-id>' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'burndown/sweep.py counts <run-id>' 'burndown/SKILL.md § The sweep'

# Idempotency: the deterministic title is the recovery, so a re-run of
# either filing moment updates the existing issue instead of filing a
# second one for the same run (Codex gate finding #2, PR #1090).
check_in "$sweep_text" 'gh issue list' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'in:title' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'not one-shot' 'burndown/SKILL.md § The sweep'

# The run report's three counts. Each needle carries the bold emphasis
# markers around its own word: a bare 'leftover' matches "leftovers" six
# times over in surrounding prose, and a bare 'standalone' matches "stay
# standalone tickets" one paragraph down — neither needle would notice its
# own sentence deleted (#1030 round-1 findings C2, S3, P3).
check_in "$sweep_text" '**fixed in-round**' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" '**leftover**' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" '**standalone**' 'burndown/SKILL.md § The sweep'

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/sweep-ticket.test.sh"
else
  exit 1
fi
