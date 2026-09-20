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
check_in "$merge_section" 'Launch at round 1' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'not when it reports "PR up"' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'backgrounding is the shell' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'there is no job id, and `status`/`result` have nothing to collect' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'each in-flight pass is a node process against the box cap' 'implement/SKILL.md § The merge'

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
# be current — including the race, which is what backgrounding introduces.
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
# The overlap is only banked when round 1 produces no fix commit.
check_in "$merge_section" 'The overlap is banked only on a round 1 whose findings produce no fix' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'is a refusal, not a pass' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'do not post that verdict, append its duration row with the refusal as the outcome' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'rerun the block here in the foreground with `phase=gate-retry`' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'either one collected looks exactly like a pass that found nothing' 'implement/SKILL.md § The merge'

# Rule 5: a collected verdict changes nothing downstream — the two-pass
# ceiling, the dispositions and the trial row are #888's and #812's still.
check_in "$merge_section" 'A collected verdict is this step' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'unchanged by where the collected pass was launched' 'implement/SKILL.md § The merge'

# Rule 5b (round 2 of the Codex pass on PR #950): the retry is the path that
# exists because the early run degraded, so it is the last place that may
# carry weaker guarantees. One block runs every phase, and the retry answers
# to the same five refusals; a retry that is itself refused ends the step as
# a visible skip with no trial row, never as a silent pass.
check_in "$merge_section" 'One recorded run, wherever it launches' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The pass runs through this block and no other' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'A second block with weaker guarantees is how a degraded run gets collected as a clean one' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'The retry is validated by the same gate' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'a rerun that errors is not a pass either' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'ends this step as `Codex pass skipped: <why>`' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'go to step 4 with no trial row' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'every started run answers to this gate' 'implement/SKILL.md § The merge'
# The phase in each filename is what keeps the retry from overwriting the
# record that justified it — both rows have to survive to be counted.
check_in "$merge_section" 'keeps a retry from overwriting the record it was run because of' 'implement/SKILL.md § The merge'

# Rule 6: every run is timed, discarded ones included, into a file that
# exists and carries the columns the row is written against.
check_in "$merge_section" 'docs/research/2026-09-20-codex-pass-durations.md' 'implement/SKILL.md § The merge'
check_in "$merge_section" '`collected`, `collected-after-retry` for a `gate-retry` that was collected, or the refusal that discarded it' 'implement/SKILL.md § The merge'
# A retry counted as a plain `collected` erases the only number this change
# produces: how often the early launch actually pays.
check_in "$merge_section" 'A retry reported as a plain `collected` loses the one number' 'implement/SKILL.md § The merge'
[ -f "$durations" ] || { echo "FAIL: missing docs/research/2026-09-20-codex-pass-durations.md" >&2; fail=1; }
if [ -f "$durations" ]; then
  for col in ticket PR phase launched completed 'duration (min)' outcome; do
    grep -qF -- "| $col |" "$durations" ||
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
