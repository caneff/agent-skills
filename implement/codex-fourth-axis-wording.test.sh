#!/usr/bin/env bash
# Guards #812/#817: the Codex adversarial-review trial runs from the
# controller, at merge time — not from the worker, at review time. This is a
# prose assertion over implement/SKILL.md, not a behavioral test — there is
# no harness that runs the skill's own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
#
# check() greps a whitespace-normalised copy of the file (newlines folded to
# spaces, runs of spaces squeezed to one), so a phrase that happens to sit
# across a prose line wrap still matches — the check pins meaning, not where
# SKILL.md's prose wraps this week.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
flat="$(tr '\n' ' ' <"$skill" | tr -s ' ')"

fail=0
check() {
  case "$flat" in
    *"$1"*) ;;
    *)
      echo "FAIL: implement/SKILL.md is missing: $1" >&2
      fail=1
      ;;
  esac
}
check_absent() {
  case "$flat" in
    *"$1"*)
      echo "FAIL: implement/SKILL.md still has the worker-side form: $1" >&2
      fail=1
      ;;
    *) ;;
  esac
}

# Rule 0: the worker's round 1 is the three Claude axes only, no fourth axis,
# no trial-row step, no Codex classes in the worker's Decisions made.
check_absent 'plus a Codex adversarial-review pass on the same diff'
check_absent 'This is a trial fourth axis on the Claude lane'
check_absent 'Every Codex finding also gets one'
check 'The Codex adversarial-review trial (#812) runs from the controller, at merge'

# Rule 1: controller step, heavy Claude-lane PRs only, in § The merge.
check '**Codex adversarial-review pass (#812 trial) — heavy Claude-lane PRs'
check "a Codex-lane build's own review step"
check "is \`codex-lane.md\`'s, unchanged"

# Rule 2: never blocks a build.
check 'Run `codex login status` first'
check 'comment `Codex pass skipped: <why>` on the PR'
check 'a skip adds no trial row'

# Rule 3: raw output is a PR comment, posted before acting on it, never /tmp.
check "Write the raw output to this workspace's git-ignored \`.scratch/\`, never"
check '`/tmp`, then post it as a PR comment before acting on it'
check '`gh pr comment <pr> --repo <owner/name> --body-file <file>`'

# Rule 4: findings hold the merge; the worker disposes of them; one re-run.
check 'No material findings → go to step 4. Findings → hold the merge'
check 'send the worker the findings and the comment URL'
check 'there is no third Codex run'

# Rule 5: the controller classifies and appends the trial row after merge.
check '`codex-only, confirmed`'
check '`also found by Claude`'
check 'append one row to'
check '`docs/research/2026-09-14-codex-review-trial.md`'
check 'This row is an'
check 'auto-ship commit on `<default>` (docs/research is not code)'

# Rule 6: the controller counts rows and brings Chris the table after five.
check "After the controller's own row brings the count to five, bring"
check 'Chris the table and a keep/drop recommendation'
check_absent '"codex trial complete" in "PR up"'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-fourth-axis-wording.test.sh"
else
  exit 1
fi
