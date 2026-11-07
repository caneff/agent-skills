#!/usr/bin/env bash
# Test fixture (#1679): a fake `gh`. Logs every call (cwd, then argv) to
# $FAKE_GH_LOG and returns a canned reply chosen by environment variables.
# FAKE_GH_OWNER_FOR="dir=login,.."  repo view: the owner, keyed on the cwd's
#                                   basename (default caneff)
# FAKE_GH_NAME_FOR="dir=name,.."    repo view: the repo name, keyed the same
#                                   way (default the cwd's basename)
# FAKE_GH_LABELS='[{"name":"a"}]'   label list (default: needs-triage only)
# FAKE_GH_PRS='[...]'               search prs (default [])
# FAKE_GH_ISSUE_STATE=OPEN|CLOSED   issue view --json state (default OPEN)
# FAKE_GH_ISSUE_STATES="42=CLOSED,43=FAIL"  per-issue override of the above;
#                                   FAIL makes that `issue view` exit 1
# FAKE_GH_ISSUE_URL=<url>           issue create prints it
# FAKE_GH_BODIES=<file>             issue create / issue comment append
#                                   "=== <argv> ===" then the --body-file's
#                                   text, so a test reads bodies in call order
# FAKE_GH_COMMENT_EXIT=<n>          issue comment exits n, posting nothing
# FAKE_GH_EXIT=<n>                  every call exits n, printing nothing
# FAKE_GH_STDERR=<text>             with FAKE_GH_EXIT, the text goes to stderr
set -euo pipefail
[ -z "${FAKE_GH_LOG:-}" ] || printf '%s\t%s\n' "$PWD" "$*" >>"$FAKE_GH_LOG"
[ -z "${FAKE_GH_EXIT:-}" ] || { [ -z "${FAKE_GH_STDERR:-}" ] || echo "$FAKE_GH_STDERR" >&2; exit "$FAKE_GH_EXIT"; }

# keyed <pairs> <key> <default>: the value <pairs> gives <key>, else <default>.
keyed() {
  local value="$3" pair
  IFS=, read -ra pairs <<<"$1"
  for pair in "${pairs[@]}"; do
    [ "${pair%%=*}" != "$2" ] || value="${pair#*=}"
  done
  printf '%s' "$value"
}

case "$1 ${2:-}" in
  "repo view")
    here="$(basename "$PWD")"
    owner="$(keyed "${FAKE_GH_OWNER_FOR:-}" "$here" caneff)"
    name="$(keyed "${FAKE_GH_NAME_FOR:-}" "$here" "$here")"
    printf '{"owner":{"id":"X","login":"%s"},"name":"%s"}\n' "$owner" "$name" ;;
  "label list")
    default='[{"name":"needs-triage"}]'
    echo "${FAKE_GH_LABELS:-$default}" ;;
  "search prs") echo "${FAKE_GH_PRS:-[]}" ;;
  "issue view")
    state="$(keyed "${FAKE_GH_ISSUE_STATES:-}" "$3" "${FAKE_GH_ISSUE_STATE:-OPEN}")"
    [ "$state" != FAIL ] || { echo "fake gh: issue view $3 failed" >&2; exit 1; }
    printf '{"state":"%s"}\n' "$state" ;;
  "issue create"|"issue comment")
    if [ "$2" = comment ] && [ -n "${FAKE_GH_COMMENT_EXIT:-}" ]; then
      echo "fake gh: issue comment failed" >&2
      exit "$FAKE_GH_COMMENT_EXIT"
    fi
    if [ -n "${FAKE_GH_BODIES:-}" ]; then
      args=("$@"); body=""
      for i in "${!args[@]}"; do
        [ "${args[$i]}" != "--body-file" ] || body="${args[$((i+1))]}"
      done
      { printf '=== %s ===\n' "$*"; cat "$body"; printf '\n'; } >>"$FAKE_GH_BODIES"
    fi
    echo "${FAKE_GH_ISSUE_URL:-https://github.com/caneff/fake/issues/1}" ;;
  *) echo "fake gh: unhandled call: $*" >&2; exit 64 ;;
esac
