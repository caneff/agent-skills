#!/usr/bin/env bash
# Prints the sandcastle-watch status line ONLY in the window whose repo has a
# live run. Scoped by cwd: reads this session's directory from the JSON Claude
# Code pipes to ccstatusline on stdin, then shows the status file that lives in
# THAT repo's .sandcastle/logs/. Other windows read a different cwd -> nothing.
cwd=$(jq -r '.cwd // .workspace.current_dir // empty' 2>/dev/null)
[ -n "$cwd" ] || exit 0
f="$cwd/.sandcastle/logs/watch-status"
[ -f "$f" ] || exit 0
# ponytail: 180s freshness guard = self-clearing if the watch loop dies uncleanly.
# if/fi (not &&) so a stale file exits 0 — a bare && leaks exit 1 to ccstatusline.
if [ $(( $(date +%s) - $(stat -c %Y "$f") )) -lt 180 ]; then cat "$f"; fi
