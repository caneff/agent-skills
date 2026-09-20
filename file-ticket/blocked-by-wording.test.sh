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
# `$2` is the heading the range stops at, or `$` for the last section — an
# unmatched end address would run the haystack to EOF and quietly widen the
# scope these needles exist to narrow.
section() {
  local end="/^## $2\$/"
  [ "$2" = '$' ] && end='$'
  sed -n "/^## $1\$/,${end}p" "$skill" | tr '\n' ' ' | tr -s ' '
}
write_text="$(section 'Write the issue' 'Create it')"
create_text="$(section 'Create it' '$')"

# § Create it is read to EOF, which is only its own scope while it is the
# last section. A section appended after it would silently widen that
# haystack, so say so here rather than let the scoping rot unnoticed.
last="$(awk '/^(```|~~~)/ { fenced = !fenced; next } !fenced && /^## / { seen = $0 } END { print seen }' "$skill")"
[ "$last" = '## Create it' ] ||
  { echo "FAIL: § Create it is no longer the last section (found: $last) — give section() its end heading" >&2; exit 1; }
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

# Two ways the section the filer wrote goes unread: a bare `Blocked by`
# heading in the pasted evidence outranks it (the reader takes the first
# visible declaration), and an unterminated fence swallows it.
check "$write_text" 'Quote every scrap of another ticket you paste' 'Write the issue'
check "$write_text" 'beats the one the skill appends below' 'Write the issue'
check "$write_text" 'indenting does not neutralise it' 'Write the issue'
check "$write_text" 'An unterminated ``` is the other way a section goes unread' 'Write the issue'
check "$write_text" 'swallows the `## Blocked by` section below' 'Write the issue'

# A native edge where the blocker is known at filing time — as well as the
# section, never instead of it, the same rule #890 gave `/to-tickets`. The
# flag is in the command template, not only in the prose under it.
check "$create_text" 'gh issue edit <n> --repo <owner>/<repo> --add-blocked-by <#>' 'Create it'
check "$create_text" 'In addition to the section, never instead of it' 'Create it'
# The edge is a second command precisely so a tracker that cannot make one
# still gets a filed, readable ticket — and so the failure is spoken aloud.
check "$create_text" 'The edge comes second' 'Create it'
check "$create_text" 'rather than a filing that never happened' 'Create it'
check "$create_text" 'Say so in your reply when the edge fails' 'Create it'

if [ "$fail" -eq 0 ]; then
  echo "PASS file-ticket/blocked-by-wording.test.sh"
else
  exit 1
fi
