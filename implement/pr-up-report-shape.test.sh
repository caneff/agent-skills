#!/usr/bin/env bash
# Guards #887: the worker's "PR up" report must state the sha its CLEAN
# reading came from, account for every commit past the last reviewed sha,
# and — when the ticket's deliverable is a test or a gate — name a mutation
# that makes it fail. From the #781 burn: 4 of 7 reports carried a tip past
# the reviewed sha and the controller diffed each by hand, and #456's CLEAN
# was already stale (true at `880aebb`, reported at `ab1100e`) by the time
# the controller read it. This is a prose assertion over implement/SKILL.md,
# not a behavioral test — there is no harness that runs the skill's own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

# Both range addresses must exist: sed does not require the end address to
# match, so a renamed `### The merge` would silently widen the range to EOF
# and every check below would read "somewhere in SKILL.md" instead.
for heading in '^### The PR$' '^### The merge$'; do
  grep -q "$heading" "$skill" || { echo "FAIL: implement/SKILL.md has no heading matching $heading" >&2; exit 1; }
done
pr_section="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill")"
[ -n "$pr_section" ] || { echo "FAIL: could not extract § The PR from implement/SKILL.md" >&2; exit 1; }
pr_flat="$(printf '%s\n' "$pr_section" | flatten)"

fail=0
check_in() {
  local section="$1" needle="$2"
  case "$section" in
    *"$needle"*) ;;
    *)
      echo "FAIL: implement/SKILL.md § The PR is missing: $needle" >&2
      fail=1
      ;;
  esac
}

# Rule 1: CLEAN carries the sha it was observed at, and the report says the
# controller's own re-check is the authority over it.
check_in "$pr_flat" 'The sha CLEAN was observed at'
check_in "$pr_flat" 'a bare "CLEAN" is a claim the controller cannot date'
check_in "$pr_flat" '§ The merge: step 2'

# Rule 2: the tip is accounted for — equal to the reviewed sha, or a stated
# diff class per commit past it, so the controller rules without diffing blind.
check_in "$pr_flat" 'the tip equals the last reviewed sha'
check_in "$pr_flat" 'diff class'
check_in "$pr_flat" 'without diffing it blind'

# Rule 2b (Codex pass on PR #908): the tip field names its source — the
# same remote `headRefOid` the CLEAN sha comes from, not a local tip — and
# each commit past the reviewed sha is cited by its own sha, so the list can
# be checked against the PR instead of taken on the worker's word.
check_in "$pr_flat" 'the same `headRefOid`'
check_in "$pr_flat" 'never your local `git rev-parse HEAD`'
check_in "$pr_flat" 'its own sha beside its diff class'

# Rule 3: a mutation check when the deliverable is a test or a gate.
check_in "$pr_flat" 'when the ticket'"'"'s deliverable is a test or a gate'
check_in "$pr_flat" 'name one change that makes the new test or gate fail'
check_in "$pr_flat" 'a test that always passes'

# Rule 4: the report template itself carries all three fields, so a worker
# copying the template cannot omit one.
template="$(printf '%s\n' "$pr_section" | sed -n '/^PR up:/,/^```$/p')"
[ -n "$template" ] || { echo "FAIL: implement/SKILL.md § The PR has no 'PR up:' report template" >&2; exit 1; }
# Same unmatched-end-address shape as the section range above: without a
# closing fence the template runs to the end of § The PR, and every field
# check below passes on prose that is not in the template at all.
case "$(printf '%s\n' "$template" | tail -n 1)" in
  '```') ;;
  *) echo "FAIL: implement/SKILL.md's 'PR up:' template has no closing fence" >&2; exit 1 ;;
esac
for field in 'Last reviewed sha:' 'CLEAN observed at:' 'Tip:' 'Mutation check:'; do
  check_in "$template" "$field"
done

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/pr-up-report-shape.test.sh"
else
  exit 1
fi
