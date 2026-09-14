#!/usr/bin/env bash
# PROTOTYPE: fire SEND prompts at workers on a schedule. usage: round.sh <round-tag> <delay1> <delay2> <delay3>
set -u
tag=$1; shift
log=$(dirname "$0")/rounds.log
i=0
for d in "$@"; do
  i=$((i+1))
  sleep "$d"
  ts=$(date -u +%FT%T.%3NZ)
  echo "$ts prompt W$i $tag" >> "$log"
  herdr agent prompt "proto-fanin-$i" "SEND $tag from W$i at $ts" >/dev/null 2>&1 &
done
wait
echo "$(date -u +%FT%T.%3NZ) round $tag done" >> "$log"
