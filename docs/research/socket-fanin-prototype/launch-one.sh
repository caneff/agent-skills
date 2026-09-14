#!/usr/bin/env bash
# PROTOTYPE (throwaway): start one claude session in its own worktree under herdr.
# usage: launch-one.sh <name>   -> prints "<name> <workspace> <pane>"
set -euo pipefail
name=$1
repo=/home/caneff/.agents/skills
wt=$repo/.claude/worktrees/$name
[ -d "$wt" ] || git -C "$repo" worktree add -q -b "$name" "$wt" origin/main
out=$(herdr worktree open --cwd "$repo" --path "$wt" --label "$name" --no-focus --trust-repository)
read -r ws pane < <(printf '%s' "$out" | python3 -c 'import sys,json; r=json.load(sys.stdin)["result"]; print(r["workspace"]["workspace_id"], r["root_pane"]["pane_id"])')
sleep 2
herdr agent start "$name" --kind claude --pane "$pane" --timeout 120000 -- --model sonnet >/dev/null
echo "$name $ws $pane"
