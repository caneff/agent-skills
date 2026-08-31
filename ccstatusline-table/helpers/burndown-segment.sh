#!/usr/bin/env bash
# ccstatusline widget: live burndown progress for the session's repo.
# Reads the Claude session JSON on stdin and renders the repo's burndown
# progress file, or nothing when no burn is live. Pass a file path as $1 to
# render that file directly (the self-check below uses this).
#
# Line grammar — a contract with burndown/SKILL.md, change in lockstep:
#   burning #<n>          claimed, build in flight
#   #<n> landed <sha>     ticket landed on main
#   #<n> parked: <why>    ticket handed to a human
#   done                  the loop stopped
if [ -n "$1" ]; then
  f=$1
else
  cwd=$(jq -r '.workspace.current_dir // .cwd // empty' 2>/dev/null)
  [ -z "$cwd" ] && exit 0
  common=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  [ -z "$common" ] && exit 0
  f="$HOME/.cache/burndown/$(basename "$(dirname "$common")").progress"
fi
[ -f "$f" ] || exit 0
# a file untouched for 12h is an abandoned burn, not a live one
[ -n "$(find "$f" -mmin -720 2>/dev/null)" ] || exit 0
last=$(tail -n 1 "$f")
[ "$last" = done ] && exit 0
landed=$(grep -c ' landed ' "$f")
parked=$(grep -c ' parked:' "$f")
cur=""
case $last in "burning #"*) cur="${last#burning } · " ;; esac
out="🔥 ${cur}${landed}✓"
[ "$parked" -gt 0 ] && out="$out ${parked}⚠"
printf '%s' "$out"
