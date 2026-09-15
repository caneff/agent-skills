#!/usr/bin/env bash
# Guards #824: Sudokumaker PR #468 wrote `Closes #462` inside backticks, so
# `gh pr view 468 --json closingIssuesReferences` was `[]` and the ticket
# never closed on merge. § Before the PR step 5 must check
# closingIssuesReferences (after the PR exists, before "PR up" goes out),
# bound its retry, and the PR body itself must carry a bare `Closes #<n>`
# line — not just the final commit body. This is a prose assertion over
# implement/SKILL.md, not a behavioral test — there is no harness that runs
# the skill's own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

before_pr_section="$(sed -n '/^### Before the PR$/,/^### The PR$/p' "$skill" | flatten)"
pr_section="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
[ -n "$before_pr_section" ] || { echo "FAIL: could not extract § Before the PR from implement/SKILL.md" >&2; exit 1; }
[ -n "$pr_section" ] || { echo "FAIL: could not extract § The PR from implement/SKILL.md" >&2; exit 1; }

fail=0
check_in() {
  local section="$1" needle="$2"
  case "$section" in
    *"$needle"*) ;;
    *)
      echo "FAIL: implement/SKILL.md is missing (in the expected section): $needle" >&2
      fail=1
      ;;
  esac
}

# Rule 1: step 5 checks closingIssuesReferences, before "PR up" goes out,
# folded into the existing isDraft/mergeStateStatus gate rather than a
# second `gh pr view` call.
check_in "$before_pr_section" 'gh pr view <pr> --repo <owner/name> --json isDraft,mergeStateStatus,closingIssuesReferences'
check_in "$before_pr_section" 'before "PR up" goes out'
check_in "$before_pr_section" 'the ticket this PR was dispatched for'

# Rule 2: a missing ticket means fix the body and re-check — but the retry
# is bounded, not an unbounded loop, and a still-missing result after one
# fix-and-recheck gets reported rather than looped on forever.
check_in "$before_pr_section" 'fix the body'
check_in "$before_pr_section" 're-run this check once'
check_in "$before_pr_section" 'stop and say so in the PR-up report rather than looping'

# Rule 3: a transient / not-yet-indexed empty result is distinguished from
# a real miss.
check_in "$before_pr_section" "GitHub not having indexed the reference yet"

# Rule 4 (controller ruling on PR #468's root cause): the PR body needs its
# own bare `Closes #<n>` line — the commit-body trailer alone left
# closingIssuesReferences empty on #827, #829 and #830.
check_in "$before_pr_section" 'and so does the PR body'
check_in "$pr_section" 'a bare line, not inside backticks or a code fence'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/closing-issue-wording.test.sh"
else
  exit 1
fi
