#!/bin/bash
# Shared body of the teaching hooks (teach-*.sh): PreToolUse(Bash) hooks that
# answer a trigger command with a section of a pointer doc as
# additionalContext, once per session per section, and never block (#1412).
# Sourced, never run.
#
# The section text is read from the doc when the hook fires, never copied
# into a hook, so the doc stays its only source. A section that cannot be
# read, and a lib that cannot be loaded, are said out loud in the context: an
# empty answer would read as "nothing to teach" (defect class 1,
# docs/agents/defect-classes.md).

teach_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
TEACH_DOCS="$(dirname "$teach_dir")"
TEACH_EVENT=${TEACH_EVENT:-PreToolUse}
# teach_fail <message>: say why nothing can be taught, without jq, and stop.
teach_fail() {
  printf '{"hookSpecificOutput": {"hookEventName": "%s", "additionalContext": "Teaching hook error: %s"}}\n' \
    "$TEACH_EVENT" "$1"
  exit 0
}
# shellcheck source=command-scan-lib.sh
. "$teach_dir/command-scan-lib.sh" 2>/dev/null \
  || teach_fail "command-scan-lib.sh is missing beside teach-lib.sh, so no teaching hook can read a command."
command -v jq >/dev/null 2>&1 \
  || teach_fail "jq is not on PATH, so no teaching hook can read its input or answer."

# One jq call for every field, NUL-separated so a command keeps its newlines.
# A subagent's calls carry its parent's session id, so the agent id joins the
# key: a reviewer's `ps` must not spend the main session's section.
mapfile -d '' -t teach_fields < <(jq -j '(.tool_input.command // ""), "\u0000",
  (.cwd // ""), "\u0000", (.session_id // "no-session"), "\u0000", (.agent_id // ""), "\u0000",
  (.source // ""), "\u0000"' 2>/dev/null)
TEACH_COMMAND=${teach_fields[0]-}
TEACH_CWD=${teach_fields[1]-}
TEACH_SESSION=$(printf '%s' "${teach_fields[2]-no-session}${teach_fields[3]:+-${teach_fields[3]}}" | tr -c 'A-Za-z0-9_-' '_')
TEACH_SOURCE=${teach_fields[4]-}
TEACH_CONTEXT=""
TEACH_PENDING=()

# The words the shell would run, one command per line: heredoc bodies,
# comments and quoted text dropped, since a trigger in any of them is data (a
# `$(...)` inside double quotes is kept: it runs). Then split at every separator, with leading `VAR=value` assignments and the
# words that only introduce a command (`if`, `{`, `sudo`, `time`, ...) taken
# off. Built on the first `runs` that gets past its word gate, since the scan
# costs time on a long command.
TEACH_SCAN=""
TEACH_RUN=""
teach_parse() {
  [ -n "$TEACH_SCAN" ] && return 0
  TEACH_SCAN=$(printf '%s\n' "$TEACH_COMMAND" | strip_heredocs)
  quote_views "$TEACH_SCAN"
  # BARE drops a `$(...)` inside double quotes, which still runs; EXPANDS
  # keeps it, so its body is added back as a command of its own.
  TEACH_RUN=$( { printf '%s\n' "$BARE"; printf '%s\n' "$EXPANDS" | grep -oE '\$\([^)]*' | cut -c3-; } | sed -E 's/(&&|\|\||[;&|()`]|\$\()/\n/g' \
    | sed -E ':a; s/^[[:space:]]+//; s/^([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*|if|then|else|elif|do|while|until|!|\{|sudo|time|env|nohup|exec|command)([[:space:]]+|$)//; ta')
}

# runs <word>...: some command in the line starts with exactly these words.
runs() {
  local w re="(^|[^A-Za-z0-9_.-])$1([^A-Za-z0-9_.-]|\$)"
  [[ "$TEACH_COMMAND" =~ $re ]] || return 1
  teach_parse
  re="^$1"
  shift
  for w in "$@"; do re+="[[:space:]]+$w"; done
  printf '%s\n' "$TEACH_RUN" | grep -qE "$re([[:space:]]|\$)"
}

teach_cache="${XDG_CACHE_HOME:-$HOME/.cache}/claude-teaching-hooks"
shown() { grep -qxF "$1" "$teach_cache/$TEACH_SESSION" 2>/dev/null; }
# A subagent's record is `<session>-<agent>`, so this names every record the
# session owns: teach-reset.sh clears them after a compaction.
session_records() { printf '%s\n' "$teach_cache/$TEACH_SESSION" "$teach_cache/$TEACH_SESSION"-*; }

# section <doc> <heading>: the body under `## <heading>`, up to the next `#`
# or `##` heading outside a code fence, leading and trailing blank lines
# dropped. Exits 2 when the doc cannot be read, 1 when it has no such heading,
# 3 when nothing is under the heading.
section() {
  [ -r "$TEACH_DOCS/$1" ] || return 2
  awk -v h="## $2" '
    $0 == h { on = found = 1; next }
    on && /^(```|~~~)/ { fence = !fence }
    on && !fence && /^##? / { exit }
    on && buf == "" && $0 !~ /[^[:space:]]/ { next }
    on { buf = buf $0 "\n"; if ($0 ~ /[^[:space:]]/) { out = buf; } }
    END { if (!found) exit 1; if (out == "") exit 3; printf "%s", out }' "$TEACH_DOCS/$1"
}

# teach <doc> <heading> <why this command>: add the section to the context,
# unless this session has already been shown it. The section, or the error saying why it is missing, counts as shown only
# once teach_emit has printed it.
teach() {
  local doc=$1 heading=$2 why=$3 key="$1#$2" text rc
  shown "$key" && return 0
  text=$(section "$doc" "$heading"); rc=$?
  # An error counts as shown too: said once, it is not repeated on every call.
  TEACH_PENDING+=("$key")
  case $rc in
    0) teach_add "Reference text from $TEACH_DOCS/$doc § $heading, shown once per session because $why:"$'\n\n'"$text" ;;
    1) teach_add "Teaching hook error: $TEACH_DOCS/$doc has no \"## $heading\" heading, so the reference text for this command is missing: the section was not found under the name this hook asks for (renamed, moved or deleted)." ;;
    2) teach_add "Teaching hook error: $TEACH_DOCS/$doc cannot be read, so the reference text for this command (§ $heading) is missing." ;;
    *) teach_add "Teaching hook error: \"## $heading\" in $TEACH_DOCS/$doc has nothing under it, so the reference text for this command is missing." ;;
  esac
}

teach_add() { TEACH_CONTEXT+="${TEACH_CONTEXT:+$'\n\n'}$1"; }

# Prints the PreToolUse answer when there is anything to say, then records
# what it printed as shown: a hook killed before this point (a timeout) has
# shown nothing and spends nothing. A denial of the same call (a permission
# prompt, a parallel blocking hook) does not drop the context: the model still
# read it, so printing is the right moment to record (#1423,
# docs/research/2026-10-04-teaching-hook-live-firing.md). Always exit 0: a
# teaching hook never blocks a command.
teach_emit() {
  local key
  [ -n "$TEACH_CONTEXT" ] || exit 0
  jq -n --arg c "$TEACH_CONTEXT" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $c}}' || exit 0
  mkdir -p "$teach_cache" 2>/dev/null || exit 0
  for key in "${TEACH_PENDING[@]}"; do printf '%s\n' "$key" >> "$teach_cache/$TEACH_SESSION"; done
  exit 0
}
