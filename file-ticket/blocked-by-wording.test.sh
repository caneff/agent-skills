#!/usr/bin/env bash
# Guards #911: every ticket `/file-ticket` creates states what it is waiting
# on, so the frontier reader can classify it. `/to-tickets` was closed by
# #890 and `/file-ticket` was the other producer left open — the ad-hoc one,
# which is where a burn's tickets come from: seven of the eight unresolved
# `ready-for-agent` tickets on this repo on 2026-09-20 were filed by hand
# during a build. This is a prose assertion over file-ticket/SKILL.md; that
# the template it ships actually parses is `file-ticket/blocked_by_test.py`.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
[ -f "$skill" ] || { echo "FAIL: missing $skill" >&2; exit 1; }

# Needles are matched against the file with its line wrapping flattened, so
# a needle can be a whole clause rather than whatever fragment happens to
# fit one line — the same shape burndown/blocked-by-grammar.test.sh uses.
skill_text="$(tr '\n' ' ' <"$skill" | tr -s ' ')"

fail=0
check() {
  case "$skill_text" in
    *"$1"*) ;;
    *) echo "FAIL: file-ticket/SKILL.md is missing: $1" >&2; fail=1 ;;
  esac
}

# The section is mandatory on every ticket, and not the filer's call.
check '**Blocked by**: a `## Blocked by` section, last in the body, on every ticket this skill files'
check 'Never omit it, and never leave it to the filer'

# The grammar is #890's, named where the filer can read it rather than
# restated here in words that could drift from the parser.
check 'one bare `#NNN` per blocking issue in this repo'
check 'None — can start immediately.'
check 'burndown/references/frontier.md'

# Silence is its own answer, which is why the section cannot be skipped.
check 'reads as **unresolved** to the frontier reader'
check 'never dispatched'

# A native edge where the blocker is known at filing time — as well as the
# section, never instead of it, the same rule #890 gave `/to-tickets`.
check '`--blocked-by <#,#>` on the create, **in addition to** the section and never instead of it'

if [ "$fail" -eq 0 ]; then
  echo "PASS file-ticket/blocked-by-wording.test.sh"
else
  exit 1
fi
