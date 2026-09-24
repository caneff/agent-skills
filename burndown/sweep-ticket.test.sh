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
# #1095: the edit targets the number the search returned; the exact-title
# filter, the result cap, the failed-search stop and the more-than-one
# refusal are each pinned by their own clause.
check_in "$sweep_text" '--json number,title' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'select(.title == "Sweep: leftovers from burn <run-id>")' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" '--limit 100' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'gh issue edit "$sweep"' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'A non-zero exit from the search stops the run' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'more than one line stops the run rather than editing a guess' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'not one-shot' 'burndown/SKILL.md § The sweep'

# #1033: a per-PR sweep found on the frontier folds into the run's own
# sweep rather than standing beside it, so the run close still files exactly
# one sweep ticket. The pointer needle checks the actual comment text, not
# only the word "pointer" — a prior draft dropped `--comment "Folded into
# <run-sweep-url>"` and this check still passed (round-1 finding C5).
check_in "$sweep_text" 'per-PR sweep' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'so fold by body instead of by run file' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'close the per-PR ticket with a pointer to the run sweep' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'comment "Folded into' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'still files this thin' 'burndown/SKILL.md § The sweep'

# #1033 verification finding C1: a later re-render at the other filing
# moment must not drop a section a fold already put in the body — the
# per-PR ticket that put it there is closed by then, off the frontier, and
# `sweep.py render` never reproduces it.
check_in "$sweep_text" 'a fold (below) put there kept as it stands' 'burndown/SKILL.md § The sweep'

# Codex gate finding 1 on PR #1094: appending the per-PR body whole would
# carry its own `## Blocked by` into the run sweep alongside the run
# sweep's own, reading AMBIGUOUS to `blocked_by_section` and dropping the
# folded sweep off the frontier for good.
check_in "$sweep_text" 'its file sections only' 'burndown/SKILL.md § The sweep'
check_in "$sweep_text" 'split("\n## Blocked by")[0]' 'burndown/SKILL.md § The sweep'

# #1130: the update path must end in exactly one `## Blocked by`, or the
# frontier reads the sweep as unresolved and never dispatches it.
check_in "$sweep_text" 'burndown/sweep.py blocked-by' 'burndown/SKILL.md § The sweep'

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
