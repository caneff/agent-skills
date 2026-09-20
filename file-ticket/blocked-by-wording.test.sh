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

# Needles are scoped to the section that owns the rule, and matched with the
# file's line wrapping flattened — the shape burndown/blocked-by-grammar.test.sh
# uses, and for its reason: a phrase as generic as "in addition to" must not
# be satisfied by unrelated prose elsewhere in the file.
section() { sed -n "/^## $1\$/,/^## $2\$/p" "$skill" | tr '\n' ' ' | tr -s ' '; }
write_text="$(section 'Write the issue' 'Create it')"
create_text="$(section 'Create it' '$')"
[ -n "$write_text" ] && [ -n "$create_text" ] ||
  { echo "FAIL: file-ticket/SKILL.md is missing § Write the issue or § Create it" >&2; exit 1; }

fail=0
check() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: file-ticket/SKILL.md § $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# The section is mandatory on every ticket, and not the filer's call.
check "$write_text" '**Blocked by**: a `## Blocked by` section, last in the body, on every ticket this skill files' 'Write the issue'
check "$write_text" "Never omit it, and never leave it to the filer's judgement" 'Write the issue'

# The grammar is #890's, named where the filer can read it rather than
# restated here in words that could drift from the parser.
check "$write_text" 'one bare `#NNN` per blocking issue **in the repo you are filing into**' 'Write the issue'
check "$write_text" 'the literal `None — can start immediately.` when nothing blocks it' 'Write the issue'
check "$write_text" 'burndown/references/frontier.md' 'Write the issue'

# Silence is its own answer, which is why the section cannot be skipped.
check "$write_text" 'reads as **unresolved** to the frontier reader' 'Write the issue'
check "$write_text" 'never dispatched' 'Write the issue'

# An unterminated fence in the pasted evidence swallows the section, so the
# ticket the filer wrote a section for still reads as silence.
check "$write_text" 'Close every code fence you paste' 'Write the issue'
check "$write_text" 'swallows the `## Blocked by` section below' 'Write the issue'

# A native edge where the blocker is known at filing time — as well as the
# section, never instead of it, the same rule #890 gave `/to-tickets`. The
# flag is in the command template, not only in the prose under it.
check "$create_text" '[--blocked-by <#,#>] \' 'Create it'
check "$create_text" '**in addition to** the section and never instead of it' 'Create it'

if [ "$fail" -eq 0 ]; then
  echo "PASS file-ticket/blocked-by-wording.test.sh"
else
  exit 1
fi
