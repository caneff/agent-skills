#!/usr/bin/env bash
# Guards #812: the Codex adversarial-review trial is a fourth review axis on
# heavy Claude-lane tickets, not a replacement for the three Claude axes, and
# it never blocks a build. This is a prose assertion over implement/SKILL.md,
# not a behavioral test — there is no harness that runs the skill's own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

fail=0
check() {
  if ! grep -qF "$1" "$skill"; then
    echo "FAIL: implement/SKILL.md is missing: $1" >&2
    fail=1
  fi
}

# Rule 1: fourth axis, not a replacement.
check 'plus `/codex:adversarial-review` on the same diff, handed'
check 'without it there is no spec check, only taste'
check 'not a replacement for the'

# Rule 2: never blocks a build.
check 'run `codex login status` first'
check 'Not logged in, or the'
check 'pass errors, skip it and name the skip in the PR body'
check '`! codex login` mid-build'

# Rule 3: finding log and classification.
check '`codex-only, confirmed`'
check '`also found by Claude`'
check 'docs/research/2026-09-14-codex-review-trial.md'

# Rule 4: trial ends after five heavy Claude-lane tickets.
check 'trial ends after five heavy Claude-lane tickets that ran the pass'
check 'a skip does not count'
check '"codex'
check 'trial complete" in "PR up"'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-fourth-axis-wording.test.sh"
else
  exit 1
fi
