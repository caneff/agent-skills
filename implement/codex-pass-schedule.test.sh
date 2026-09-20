#!/usr/bin/env bash
# Guards #942: where the Codex adversarial pass fires, and what collecting
# it costs. It used to launch at "PR up", so it was pure serial time bolted
# onto the merge gate, after three opus axes and a verification pass had
# already read the same diff; it now launches at the worker's "Round 1 out"
# wake and overlaps the verification pass instead. That is only safe behind
# a fail-closed collection gate: with the run detached, a verdict nobody
# could collect looks exactly like a pass that found nothing, which is the
# absent-answer-read-as-benign shape this repo closed seven times on
# 2026-09-20. So the gate must refuse — not merge — on a verdict that is
# absent, unreadable, raced (the branch moved while Codex was reading) or
# stale (it does not match the PR's `headRefOid`), and a discarded verdict
# must never be posted as if it described this PR. The measurement gap goes
# with it: every run records its own duration, since five passes on
# 2026-09-20 could only be bounded by output-file timestamps.
# This is a prose assertion over implement/SKILL.md plus an existence check
# on the durations file — there is no harness that runs the skill's own
# prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
# Section-scoped like codex-fourth-axis-wording.test.sh: the launch trigger
# is the worker's § Review (a wake it sends, not a pass it runs — #817
# still holds), and the gate is the controller's § The merge.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
repo="$(cd "$here/.." && pwd)"
durations="$repo/docs/research/2026-09-20-codex-pass-durations.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

review_section="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
merge_section="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
[ -n "$review_section" ] || { echo "FAIL: could not extract § Review from implement/SKILL.md" >&2; exit 1; }
[ -n "$merge_section" ] || { echo "FAIL: could not extract § The merge from implement/SKILL.md" >&2; exit 1; }

fail=0
check_in() {
  local section="$1" needle="$2" where="$3"
  case "$section" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}
check_absent_in() {
  local section="$1" needle="$2" where="$3"
  case "$section" in
    *"$needle"*) echo "FAIL: $where still has: $needle" >&2; fail=1 ;;
    *) ;;
  esac
}

# Rule 1: the worker sends the wake that launches the pass, before its own
# verification pass — that ordering is the whole saving.
check_in "$review_section" 'Round 1 out: <k> findings, head <sha>' 'implement/SKILL.md § Review'
check_in "$review_section" 'before starting the verification pass' 'implement/SKILL.md § Review'
check_in "$review_section" 'sending it late costs the overlap it exists to buy' 'implement/SKILL.md § Review'

# Rule 2: the controller launches on that wake, not at "PR up", in a
# backgrounded shell — because the script's own `--background` is parsed
# and never read, so no job id exists to collect through status/result.
check_in "$merge_section" 'Launch at round 1, collect here' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'not when it reports "PR up"' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'backgrounding is the shell' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'there is no job id, and `status`/`result` have nothing to collect' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'each in-flight pass is a node process against the box cap' 'implement/SKILL.md § The merge'

# Rule 3: the launched pass writes outside the workspace — the worker's own
# Before the PR step deletes `.scratch/`, which would take an in-flight
# pass's output with it — into the #855 review-cache directory.
check_in "$merge_section" '`~/.cache/agent-reviews/<repo>/`, never this workspace' 'implement/SKILL.md § The merge'
check_in "$merge_section" "the worker's own § Before the PR step 3 deletes it" 'implement/SKILL.md § The merge'
check_in "$merge_section" 'codex-adversarial-<n>.json' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'the workspace HEAD at launch and again at completion' 'implement/SKILL.md § The merge'

# Rule 4: the gate is fail-closed, and names every way a verdict fails to
# be current — including the race, which is what backgrounding introduces.
check_in "$merge_section" 'The gate is fail-closed' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'launch sha, completion sha and the PR' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'Absent, unreadable, raced' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'is a refusal, not a pass' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'discard that verdict, do not post it to the PR' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'run the pass here, against the current head, as the first pass' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'a verdict nobody could collect looks exactly like a pass that found nothing' 'implement/SKILL.md § The merge'

# Rule 5: a collected verdict changes nothing downstream — the two-pass
# ceiling, the dispositions and the trial row are #888's and #812's still.
check_in "$merge_section" 'A collected verdict is this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'unchanged by where it was launched' 'implement/SKILL.md § The merge'

# Rule 6: every run is timed, discarded ones included, into a file that
# exists and carries the columns the row is written against.
check_in "$merge_section" 'docs/research/2026-09-20-codex-pass-durations.md' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'collected, or why it was discarded' 'implement/SKILL.md § The merge'
[ -f "$durations" ] || { echo "FAIL: missing docs/research/2026-09-20-codex-pass-durations.md" >&2; fail=1; }
if [ -f "$durations" ]; then
  for col in ticket PR pass launched completed 'duration (min)' outcome; do
    grep -qF -- "| $col |" "$durations" ||
      grep -qF -- "$col |" "$durations" ||
      { echo "FAIL: durations file has no '$col' column" >&2; fail=1; }
  done
fi

# Rule 7: the old unconditional shape is gone — the pass is no longer
# described as starting at the merge gate by default.
check_absent_in "$merge_section" 'Otherwise, from this PR' 'implement/SKILL.md § The merge'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-pass-schedule.test.sh"
else
  exit 1
fi
