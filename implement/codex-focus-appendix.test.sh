#!/usr/bin/env bash
# Guards #941: `adversarial-review` reads one branch against
# `origin/<default>` and can see nothing else — not a sibling branch holding
# half of a deliberately split change, and not the fact that the code under
# review is parked or otherwise landing ahead of its own activation. Both
# gaps it reports as a missing requirement: right about `main`, wrong about
# the work. The remedy is context the controller already holds at
# dispatch time, appended to the focus text, so both required lines must be
# named in both invocation sites and both must be written out even when
# there is nothing to report — an omitted line and a "nothing is split"
# line read the same to Codex.
# This is a prose assertion over implement/SKILL.md and
# implement/codex-lane.md, not a behavioral test — there is no harness that
# runs the skills' own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
# Section-scoped for SKILL.md, the way codex-wave.test.sh is:
# the appendix belongs to § The Codex pass (the review wave's Codex block,
# #1401), and a whole-file check would still pass with it pasted anywhere at
# all.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
lane="$here/codex-lane.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

merge_section="$(sed -n '/^#### The Codex pass$/,/^### Before the PR$/p' "$skill" | flatten)"
[ -n "$merge_section" ] || { echo "FAIL: could not extract § The Codex pass from implement/SKILL.md" >&2; exit 1; }
lane_flat="$(flatten <"$lane")"

fail=0
check_in() {
  local section="$1" needle="$2" where="$3"
  case "$section" in
    *"$needle"*) ;;
    *)
      echo "FAIL: $where is missing: $needle" >&2
      fail=1
      ;;
  esac
}

# Rule 1: the appendix exists, is named as controller context rather than
# ticket text, and is appended to the same body_file the pass already reads.
check_in "$merge_section" 'Context from the worker'"'"'s brief — not part of the ticket' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" 'appended to `body_file` after the rendered ticket' 'implement/SKILL.md § The Codex pass'

# Rule 2: both required lines, by name.
check_in "$merge_section" '**Open sibling branches.**' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" '**Posture.**' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" 'which file, which line, which PR' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" 'landing ahead of its own activation, and the ticket that activates it' 'implement/SKILL.md § The Codex pass'

# Rule 3: the "nothing to report" case is written out, not omitted — the
# absent answer read as the benign one is the shape this lane keeps closing.
check_in "$merge_section" 'No sibling branch is open, and nothing in this PR is split.' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" 'its posture is what the tree implies' 'implement/SKILL.md § The Codex pass'
check_in "$merge_section" 'Both lines are written even when there is nothing to report' 'implement/SKILL.md § The Codex pass'

# Rule 4: the appendix is written with the file-write tool, like the ticket
# render it follows — a sibling branch name or a ticket title reaching the
# shell as an interpolated string is the same injection the ticket body was
# already protected from.
check_in "$merge_section" 'Write both lines with your file-write tool, into the same file, never interpolated' 'implement/SKILL.md § The Codex pass'

# Rule 5: the Codex lane's own invocation carries the same appendix, and
# its worker — who does not hold either fact — asks the controller rather
# than inferring them from the tree, the one source that cannot see them.
check_in "$lane_flat" 'the same two-line context appendix' 'implement/codex-lane.md'
check_in "$lane_flat" '**Open sibling branches.** and **Posture.**' 'implement/codex-lane.md'
check_in "$lane_flat" 'which is the one copy of it; a second copy here would drift' 'implement/codex-lane.md'
check_in "$lane_flat" 'ask the controller for both before you compose the file' 'implement/codex-lane.md'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-focus-appendix.test.sh"
else
  exit 1
fi
