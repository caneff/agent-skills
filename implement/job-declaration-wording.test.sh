#!/usr/bin/env bash
# Guards #1311: `runfile.py clump` records job `none` at registration, so a
# job a worker launches before its "PR up" is charged zero unless the worker
# says so first (Codex gate on PR #1338, defect class 2: a stated fallback
# with no mechanism behind it). The worker half lives in implement/SKILL.md
# § Control, the controller half in burndown/SKILL.md § Liveness. This is a
# prose assertion, not a behavioural test: no harness runs the skill's own
# prose.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
implement="$here/SKILL.md"
burndown="$here/../burndown/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

control_section="$(sed -n '/^## Control$/,/^## Light tier$/p' "$implement" | flatten)"
declares_section="$(sed -n '/^\*\*A worker declares its job size\.\*\*/,/^The charge is arithmetic/p' "$burndown" | flatten)"
[ -n "$control_section" ] || { echo "FAIL: could not extract § Control from implement/SKILL.md" >&2; exit 1; }
[ -n "$declares_section" ] || { echo "FAIL: could not extract 'A worker declares its job size' from burndown/SKILL.md" >&2; exit 1; }

fail=0
check_in() {
  local section="$1" needle="$2" where="$3"
  case "$section" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Worker half (#1339): the worker writes its own job record under the run-file
# lock before it launches, so no controller turn sits between the launch and
# the record; the message to the controller is only a notice.
check_in "$control_section" 'Declare a parallel job before you launch it' 'implement/SKILL.md § Control'
check_in "$control_section" 'past one core' 'implement/SKILL.md § Control'
check_in "$control_section" 'runfile.py job <run-id> --clump <n> --cores <k>' 'implement/SKILL.md § Control'
check_in "$control_section" 'under the run-file lock, before you launch' 'implement/SKILL.md § Control'
check_in "$control_section" 'run the same line with `--done`' 'implement/SKILL.md § Control'
check_in "$control_section" 'If `runfile.py` refuses' 'implement/SKILL.md § Control'
check_in "$control_section" 'do not launch: send the controller the refusal' 'implement/SKILL.md § Control'
check_in "$control_section" 'launch on that reply' 'implement/SKILL.md § Control'
check_in "$control_section" 'a notice, not the record' 'implement/SKILL.md § Control'
check_in "$control_section" 'no `--run <run-id>`' 'implement/SKILL.md § Control'
check_in "$control_section" 'the "PR up" `Parallel jobs` line stays' 'implement/SKILL.md § Control'

# Controller half: the worker's write is the primary record; the controller's
# own `runfile.py job` is the fallback.
check_in "$declares_section" 'writes its own record' 'burndown/SKILL.md § Liveness'
check_in "$declares_section" 'fallback' 'burndown/SKILL.md § Liveness'
check_in "$declares_section" 'on arrival' 'burndown/SKILL.md § Liveness'
check_in "$declares_section" 'a worker declares a job past one core before it launches it' 'burndown/SKILL.md § Liveness'

[ "$fail" -eq 0 ] || exit 1
echo "PASS: implement/SKILL.md and burndown/SKILL.md carry the launch-time job declaration"
