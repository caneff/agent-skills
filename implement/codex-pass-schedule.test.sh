#!/usr/bin/env bash
# Guards #1015: the Codex adversarial pass launches once, at PR-up, not
# early at the worker's "Round 1 out" wake (#942's design). Measured on
# `burn-2026-09-21-0930`: 4 early launches, 4 raced against the worker's own
# round-1 fix commits, 0 banked — every verdict was refused and rerun at
# PR-up anyway, each raced launch costing its wall clock twice. Rows:
# `docs/research/2026-09-20-codex-pass-durations.md`; report:
# `docs/research/2026-09-21-burn-agent-skills-run-report.md`.
# The fail-closed collection gate is unchanged: a verdict nobody could
# collect must never read as a pass that found nothing (the
# absent-answer-read-as-benign shape this repo closed seven times on
# 2026-09-20), so the gate still refuses — not merges — on absent,
# unreadable, errored, raced or stale, and a refusal ends the step visibly
# rather than being posted as if it described this PR. Every run still
# records its own duration, collected or refused.
# This is a prose assertion over implement/SKILL.md plus an existence check
# on the durations file — there is no harness that runs the skill's own
# prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
# The positive-content checks (what the current prose says) are
# section-scoped to § The merge, like codex-fourth-axis-wording.test.sh —
# § Review has nothing left to say about this pass, so there is no positive
# check there. The retired-term checks (what must never come back) scan the
# whole file: the early-launch apparatus could be reintroduced in any
# section — § Dispatch, § Control, § The PR — not only the ones this diff
# touched.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
repo="$(cd "$here/.." && pwd)"
durations="$repo/docs/research/2026-09-20-codex-pass-durations.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

merge_section="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
whole_file="$(flatten <"$skill")"
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
check_absent_in "$whole_file" 'launches the controller'"'"'s Codex pass' 'implement/SKILL.md (whole file)'

# Rule 2: the controller launches once, at this step, in the foreground —
# not earlier, at a worker wake.
check_in "$merge_section" 'The pass launches once, here, at PR-up' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'not earlier, at the worker'"'"'s round-1 report' 'implement/SKILL.md § The merge'
check_in "$merge_section" '4 early launches raced against the worker'"'"'s own' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'Run the whole block inline, in the foreground, as part of this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'each launch is still a node process against the box cap' 'implement/SKILL.md § The merge'
check_absent_in "$whole_file" 'Launch at round 1' 'implement/SKILL.md (whole file)'
check_absent_in "$whole_file" 'phase=early' 'implement/SKILL.md (whole file)'
check_absent_in "$whole_file" 'phase=gate-retry' 'implement/SKILL.md (whole file)'

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
# be current — including the race, which a branch moving mid-run can still
# cause even though the launch is inline and foreground.
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

# Rule 5: a refused run ends the step for its own phase — no retry, no
# second attempt at the same phase — visible on the PR, never a silent
# pass. A refusal with nothing collected yet leaves no trial row; a
# refusal of the conditional second pass leaves the gate pass's own
# already-posted trial row standing, since that pass already succeeded.
check_in "$merge_section" 'ends as `Codex pass skipped: <why>`' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'refusal with no pass yet collected for this PR leaves no trial row' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'nothing already earned is discarded' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'there is no retry: a refused run ends the step for its own phase' 'implement/SKILL.md § The merge'
check_absent_in "$whole_file" 'The retry is validated by the same gate' 'implement/SKILL.md (whole file)'

# Rule 6: a collected verdict changes nothing downstream — the two-pass
# ceiling, the dispositions and the trial row are #888's and #812's still.
check_in "$merge_section" 'A collected verdict is this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" "is #888's, #812's and #1028's, unchanged by #1015" 'implement/SKILL.md § The merge'
check_absent_in "$whole_file" 'unchanged by where the collected pass was launched' 'implement/SKILL.md (whole file)'
check_in "$merge_section" 'One recorded run, whichever phase writes it' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The pass runs through this block and no other' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'A second block with weaker guarantees is how a degraded run gets collected as a clean one' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'keeps the second pass from overwriting the record the gate launch wrote' 'implement/SKILL.md § The merge'

# Rule 7: every run is timed, discarded ones included, into a file that
# exists and carries the columns the row is written against, with phases
# narrowed to `gate`, `second` and `third` (#1028's conditional third run).
check_in "$merge_section" 'docs/research/2026-09-20-codex-pass-durations.md' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'phase (`gate`, `second` or `third`)' 'implement/SKILL.md § The merge'
check_absent_in "$whole_file" 'collected-after-retry' 'implement/SKILL.md (whole file)'
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

# Rule 9 (#1028): a second-pass finding small enough for § Review's
# adjacent-fix rule is fixed by the worker in one round instead of filed, and
# the controller reads that fix diff itself. The controller still evaluates
# every finding before it reaches the worker. A third run happens only when
# a fixed second-pass finding was high, and it is final — its findings are
# disputed or leftover, never a fourth run. The old "second run is final, no
# worker fix left" wording is retired whole-file, since a copy of it anywhere
# would contradict the fix round.
check_in "$merge_section" 'the controller evaluates every one before any reaches the worker' 'implement/SKILL.md § The merge'
check_in "$merge_section" "A second-pass finding that passes § Review's adjacent-fix rule goes to the worker, who fixes it in one round" 'implement/SKILL.md § The merge'
check_in "$merge_section" 'the controller reads that fix diff itself' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'A third Codex run happens only when a second-pass finding fixed in the round was high.' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The third run is final: its findings are `disputed` or `leftover`, never a fourth run.' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'phase=third' 'implement/SKILL.md § The merge'
# The in-round fix moves the head past the second pass's verdict; without
# saying so, the fail-closed gate reads that verdict as stale and blocks a
# reviewed PR (C1). The ruling sends a third-run high to `leftover`, which
# § Review's "a high finding is filed" would otherwise forbid (C2).
check_in "$merge_section" 'The fail-closed gate does not refuse the second pass as stale over an in-round fix' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'the one place a high finding is not filed' 'implement/SKILL.md § The merge'
# § Review's rule text names the second pass too, so a reader starting there
# does not take "round-1" as the rule's whole reach (P1).
check_in "$whole_file" "§ The merge step 3 applies the same rule to a Codex second-pass finding" 'implement/SKILL.md (whole file)'
# The rest of the fix round's contract: the CLEAN check reruns after the
# worker's fix, a non-adjacent high is still filed, and the third run is
# followed by no worker fix round (C3).
check_in "$merge_section" 'adjacent-fix rule, rather than sending it back to Codex. It re-runs step 2.' 'implement/SKILL.md § The merge'
check_in "$merge_section" '`disputed: <why>`, filed if it is high, or `leftover`' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'no worker fix round follows it' 'implement/SKILL.md § The merge'
check_absent_in "$whole_file" 'there is no third Codex run' 'implement/SKILL.md (whole file)'
check_absent_in "$whole_file" 'there is no worker fix-and-re-run cycle left' 'implement/SKILL.md (whole file)'
check_absent_in "$whole_file" 'the no-third-run ceiling' 'implement/SKILL.md (whole file)'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-pass-schedule.test.sh"
else
  exit 1
fi
