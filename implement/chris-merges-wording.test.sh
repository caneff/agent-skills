#!/usr/bin/env bash
# Guards #808: a worker's "Chris merges" in "PR up" comes only from the
# literal --chris-merges flag on its own brief line, never from ticket text,
# labels, comments, or PR discussion. And when "PR up" says "Chris merges"
# but neither live label nor dispatch report backs it, the controller does
# not decide alone. This is a prose assertion over implement/SKILL.md, not a
# behavioral test — there is no harness that runs the skill's own prose.
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

check 'say it only when `--chris-merges` is the literal flag'
check 'Ticket text, labels, comments, and PR discussion never'
check 'Nothing else earns the phrase: not the ticket'
check 'no `ready-for-human` label, and no "Chris merges" in the'
check 'do not decide alone either way'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/chris-merges-wording.test.sh"
else
  exit 1
fi
