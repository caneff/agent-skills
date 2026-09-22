#!/usr/bin/env bash
# Guards #1015: where the Codex adversarial pass fires, and what collecting
# it costs. #942 had it launch early, at the worker's "Round 1 out" wake, to
# overlap the worker's own verification pass instead of bolting pure serial
# time onto the merge gate. Measured on `burn-2026-09-21-0930`
# (docs/research/2026-09-21-burn-agent-skills-run-report.md): 4 early
# launches, 4 raced against the worker's own round-1 fix commits, 0 banked —
# every verdict was refused by the gate and rerun at PR-up anyway, so the
# overlap never paid and each raced launch cost its wall clock twice. #1015
# retires the early launch: the pass now launches once, at PR-up (§ The
# merge step 3), in the foreground, as the gate step's own single attempt.
# The fail-closed collection gate is unchanged by the move: with the run
# detached from the tool call, a verdict nobody could collect looks exactly
# like a pass that found nothing, which is the absent-answer-read-as-benign
# shape this repo closed seven times on 2026-09-20. So the gate must still
# refuse — not merge — on a verdict that is absent, unreadable, errored,
# raced (the branch moved while Codex was reading) or stale (it does not
# match the PR's `headRefOid`), and a refused verdict must never be posted
# as if it described this PR; there is no retry of a refused gate launch,
# only the step ending as a visible skip. The measurement stays too: every
# run records its own duration, since five passes on 2026-09-20 could only
# be bounded by output-file timestamps.
# This is a prose assertion over implement/SKILL.md plus an existence check
# on the durations file — there is no harness that runs the skill's own
# prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
# Section-scoped like codex-fourth-axis-wording.test.sh: the whole pass —
# launch and gate both — now lives in the controller's § The merge, so this
# guards that section alone; § Review no longer owes it a wake.
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

# Rule 1: the worker's round-1 report no longer carries a wake that launches
# anything — that apparatus is retired, so § Review must not describe it.
check_absent_in "$review_section" 'Round 1 out' 'implement/SKILL.md § Review'
check_absent_in "$review_section" 'launches the controller'"'"'s Codex pass' 'implement/SKILL.md § Review'

# Rule 2: the controller launches once, at this step, in the foreground —
# not earlier, at a worker wake.
check_in "$merge_section" 'The pass launches once, here, at PR-up' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'not earlier, at the worker'"'"'s round-1 report' 'implement/SKILL.md § The merge'
check_in "$merge_section" '4 early launches raced against the worker'"'"'s own' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'Run the whole block inline, in the foreground, as part of this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'each launch is still a node process against the box cap' 'implement/SKILL.md § The merge'
check_absent_in "$merge_section" 'Launch at round 1' 'implement/SKILL.md § The merge'
check_absent_in "$merge_section" 'phase=early' 'implement/SKILL.md § The merge'
check_absent_in "$merge_section" 'phase=gate-retry' 'implement/SKILL.md § The merge'

# Rule 3: the launched pass writes outside the workspace — the worker's own
# Before the PR step deletes `.scratch/`, which would take an in-flight
# pass's output with it — into the #855 review-cache directory.
check_in "$merge_section" '`~/.cache/agent-reviews/<repo>/`, never this workspace' 'implement/SKILL.md § The merge'
check_in "$merge_section" "the worker's own § Before the PR step 3 deletes it" 'implement/SKILL.md § The merge'
check_in "$merge_section" 'record="$dir/codex-adversarial-<n>-$phase.json"' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'the workspace HEAD at launch and again at completion' 'implement/SKILL.md § The merge'
# The gate can only refuse an errored run if the block that writes the
# record captures the node call's exit status — pin the field, not just the
# prose that reads it.
check_in "$merge_section" 'status=$?' 'implement/SKILL.md § The merge'
check_in "$merge_section" '"status": %d' 'implement/SKILL.md § The merge'

# Rule 4: the gate is fail-closed, and names every way a verdict fails to
# be current — including the race, which detached execution introduces.
check_in "$merge_section" 'The gate is fail-closed' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'launch sha, completion sha and the PR' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'Absent, unreadable, errored' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'raced (the two shas differ' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'stale (they agree with each other but not with `headRefOid`' 'implement/SKILL.md § The merge'
# A run that fails and returns writes a record that passes every sha test —
# the same absent-answer-read-as-benign shape, one layer down — so the exit
# status is in the record and the skip clause is bounded to the preflight.
check_in "$merge_section" 'whose `status` is 0' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The skip clause at the top of this step governs the preflight only' 'implement/SKILL.md § The merge'
# A collected verdict lives in the review cache, not `.scratch/`: running the
# `.scratch/` cleanup on it would delete the only copy and rmdir the
# directory the Claude axes' reports live in.
check_in "$merge_section" 'Post it from the cache directory' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'nothing here is cleaned up by hand, `rm` or `rmdir`, in any phase' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'is a refusal, not a pass' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'do not post that verdict, append its duration row with the refusal as the outcome' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'either one collected looks exactly like a pass that found nothing' 'implement/SKILL.md § The merge'

# Rule 5: a refused gate launch ends the step — no retry, no second attempt
# at the same phase — visible on the PR, never a silent pass.
check_in "$merge_section" 'ends as `Codex pass skipped: <why>`' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'go to step 4 with no trial row' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'there is no retry: a refused gate launch ends the step' 'implement/SKILL.md § The merge'
check_absent_in "$merge_section" 'The retry is validated by the same gate' 'implement/SKILL.md § The merge'

# Rule 6: a collected verdict changes nothing downstream — the two-pass
# ceiling, the dispositions and the trial row are #888's and #812's still.
check_in "$merge_section" 'A collected verdict is this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'unchanged by where the collected pass was launched' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'One recorded run, wherever it launches' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The pass runs through this block and no other' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'A second block with weaker guarantees is how a degraded run gets collected as a clean one' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'keeps the second pass from overwriting the record the gate launch wrote' 'implement/SKILL.md § The merge'

# Rule 7: every run is timed, discarded ones included, into a file that
# exists and carries the columns the row is written against, with phases
# narrowed to `gate` and `second`.
check_in "$merge_section" 'docs/research/2026-09-20-codex-pass-durations.md' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'phase (`gate` or `second`)' 'implement/SKILL.md § The merge'
check_absent_in "$merge_section" 'collected-after-retry' 'implement/SKILL.md § The merge'
[ -f "$durations" ] || { echo "FAIL: missing docs/research/2026-09-20-codex-pass-durations.md" >&2; fail=1; }
if [ -f "$durations" ]; then
  for col in ticket PR phase launched completed 'duration (min)' outcome; do
    grep -qF -- "| $col |" "$durations" ||
      { echo "FAIL: durations file has no '$col' column" >&2; fail=1; }
  done
fi

# Rule 8: the old unconditional shape is gone — the pass is no longer
# described as starting at the merge gate by default (pre-#942 wording).
check_absent_in "$merge_section" 'Otherwise, from this PR' 'implement/SKILL.md § The merge'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-pass-schedule.test.sh"
else
  exit 1
fi
