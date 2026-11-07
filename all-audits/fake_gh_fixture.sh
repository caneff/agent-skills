#!/usr/bin/env bash
# Test fixture (#1679): a fake `gh`. Logs every call (cwd, then argv) to
# $FAKE_GH_LOG and returns a canned reply chosen by environment variables.
# Later tickets extend it.
# FAKE_GH_OWNER=<login>            repo view --json owner (default caneff)
# FAKE_GH_OWNER_FOR="dir=login,.." per-directory override, keyed on the cwd's basename
# FAKE_GH_LABELS='["a","b"]'       label list --json name (default [])
# FAKE_GH_PRS='[...]'              pr list / search prs (default [])
# FAKE_GH_ISSUE_STATE=OPEN|CLOSED  issue view --json state (default OPEN)
# FAKE_GH_ISSUE_URL=<url>          issue create prints it
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
  "label list") echo "${FAKE_GH_LABELS:-[]}" ;;
  "pr list"|"search prs") echo "${FAKE_GH_PRS:-[]}" ;;
  "issue view") printf '{"state":"%s"}\n' "${FAKE_GH_ISSUE_STATE:-OPEN}" ;;
  "issue create") echo "${FAKE_GH_ISSUE_URL:-https://github.com/caneff/fake/issues/1}" ;;
  *) echo "fake gh: unhandled call: $*" >&2; exit 64 ;;
esac
