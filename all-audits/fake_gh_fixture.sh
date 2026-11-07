#!/usr/bin/env bash
# Test fixture (#1679): a fake `gh`. Logs every call (cwd, then argv) to
# $FAKE_GH_LOG and returns a canned reply chosen by environment variables.
# Later tickets extend it.
# FAKE_GH_OWNER=<login>            repo view --json owner (default caneff)
# FAKE_GH_OWNER_FOR="dir=login,.." per-directory override, keyed on the cwd's basename
# FAKE_GH_LABELS='[{"name":"a"}]'  label list --json name (default: needs-triage only)
# FAKE_GH_PRS='[...]'              pr list / search prs (default [])
# FAKE_GH_ISSUE_STATE=OPEN|CLOSED  issue view --json state (default OPEN)
# FAKE_GH_ISSUE_URL=<url>          issue create prints it
# FAKE_GH_BODIES=<file> (#1680)    issue create / issue comment append "=== <argv> ===", then the
#                                  --body-file's text, so a test reads the bodies in call order
# FAKE_GH_EXIT=<n>                 every call exits n, printing nothing
# FAKE_GH_STDERR=<text>            with FAKE_GH_EXIT, the text goes to stderr
set -euo pipefail
[ -z "${FAKE_GH_LOG:-}" ] || printf '%s\t%s\n' "$PWD" "$*" >>"$FAKE_GH_LOG"
[ -z "${FAKE_GH_EXIT:-}" ] || { [ -z "${FAKE_GH_STDERR:-}" ] || echo "$FAKE_GH_STDERR" >&2; exit "$FAKE_GH_EXIT"; }
case "$1 ${2:-}" in
  "repo view")
    owner="${FAKE_GH_OWNER:-caneff}"
    here="$(basename "$PWD")"
    IFS=, read -ra pairs <<<"${FAKE_GH_OWNER_FOR:-}"
    for pair in "${pairs[@]}"; do
      [ "${pair%%=*}" != "$here" ] || owner="${pair#*=}"
    done
    printf '{"owner":{"id":"X","login":"%s"}}\n' "$owner" ;;
  "label list")
    default='[{"name":"needs-triage"}]'
    echo "${FAKE_GH_LABELS:-$default}" ;;
  "pr list"|"search prs") echo "${FAKE_GH_PRS:-[]}" ;;
  "issue view") printf '{"state":"%s"}\n' "${FAKE_GH_ISSUE_STATE:-OPEN}" ;;
  "issue create"|"issue comment")
    if [ -n "${FAKE_GH_BODIES:-}" ]; then
      args=("$@"); body=""
      for i in "${!args[@]}"; do [ "${args[$i]}" != "--body-file" ] || body="${args[$((i+1))]}"; done
      { printf '=== %s ===\n' "$*"; cat "$body"; printf '\n'; } >>"$FAKE_GH_BODIES"
    fi
    echo "${FAKE_GH_ISSUE_URL:-https://github.com/caneff/fake/issues/1}" ;;
  *) echo "fake gh: unhandled call: $*" >&2; exit 64 ;;
esac
