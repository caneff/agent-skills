#!/bin/bash
# Shared body of the teaching hooks (teach-*.sh): PreToolUse(Bash) hooks that
# answer a trigger command with a section of a pointer doc as
# additionalContext, once per session per section, and never block (#1412).
# Sourced, never run.
#
# The section text is read from the doc when the hook fires, never copied
# into a hook, so the doc stays its only source. A section that cannot be
# found is said out loud in the context: an empty answer would read as
# "nothing to teach" (defect class 1, docs/agents/defect-classes.md).

teach_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
TEACH_DOCS="$(dirname "$teach_dir")"
# shellcheck source=command-scan-lib.sh
. "$teach_dir/command-scan-lib.sh" || exit 0

TEACH_INPUT=$(cat)
TEACH_COMMAND=$(printf '%s' "$TEACH_INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)
TEACH_CWD=$(printf '%s' "$TEACH_INPUT" | jq -r '.cwd // ""' 2>/dev/null)
TEACH_SESSION=$(printf '%s' "$TEACH_INPUT" | jq -r '.session_id // "no-session"' 2>/dev/null | tr -c 'A-Za-z0-9_-' '_')
TEACH_CONTEXT=""

# The words the shell would run, one command per line: heredoc bodies and
# quoted text dropped (a trigger in either is data), then split at every
# separator, with leading `VAR=value` assignments taken off each command.
TEACH_SCAN=$(printf '%s\n' "$TEACH_COMMAND" | strip_heredocs)
quote_views "$TEACH_SCAN"
TEACH_RUN=$(printf '%s\n' "$BARE" | sed -E 's/(&&|\|\||[;&|()`]|\$\()/\n/g' \
  | sed -E 's/^[[:space:]]+//; :a; s/^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+//; ta')

# runs <word>...: some command in the line starts with exactly these words.
runs() {
  local re="^$1"
  shift
  for w in "$@"; do re+="[[:space:]]+$w"; done
  printf '%s\n' "$TEACH_RUN" | grep -qE "$re([[:space:]]|\$)"
}

teach_cache="${XDG_CACHE_HOME:-$HOME/.cache}/claude-teaching-hooks"
shown() { grep -qxF "$1" "$teach_cache/$TEACH_SESSION" 2>/dev/null; }
mark_shown() { mkdir -p "$teach_cache" 2>/dev/null && printf '%s\n' "$1" >> "$teach_cache/$TEACH_SESSION"; }

# section <doc> <heading>: the body under `## <heading>`, up to the next `#`
# or `##` heading, leading and trailing blank lines dropped. Fails when there is no such
# heading or nothing under it.
section() {
  awk -v h="## $2" '
    $0 == h { on = 1; next }
    on && /^##? / { exit }
    on && buf == "" && $0 !~ /[^[:space:]]/ { next }
    on { buf = buf $0 "\n"; if ($0 ~ /[^[:space:]]/) { out = buf; } }
    END { if (out == "") exit 1; printf "%s", out }' "$TEACH_DOCS/$1"
}

# teach <doc> <heading> <why this command>: add the section to the context,
# unless this session has already been shown it. Returns 1 when it was
# already shown, so a hook can skip work that only goes with the section.
teach() {
  local doc=$1 heading=$2 why=$3 key="$1#$2" text
  shown "$key" && return 1
  if ! text=$(section "$doc" "$heading"); then
    teach_add "Teaching hook error: section \"## $heading\" was not found in $TEACH_DOCS/$doc, so the reference text for this command is missing. The heading was renamed or removed; the hook and the doc disagree."
    return 0
  fi
  mark_shown "$key"
  teach_add "Reference text from $TEACH_DOCS/$doc § $heading, shown once per session because $why:"$'\n\n'"$text"
}

teach_add() { TEACH_CONTEXT+="${TEACH_CONTEXT:+$'\n\n'}$1"; }

# Prints the PreToolUse answer when there is anything to say. Always exit 0:
# a teaching hook never blocks a command.
teach_emit() {
  [ -n "$TEACH_CONTEXT" ] || exit 0
  jq -n --arg c "$TEACH_CONTEXT" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $c}}'
  exit 0
}
