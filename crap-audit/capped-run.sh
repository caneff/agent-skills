#!/usr/bin/env bash
# Run a command in a transient systemd user unit with a hard memory cap and no
# swap, so a runaway instrumented test suite is reported as an OOM kill of that
# unit instead of taking the WSL VM down (#1667).
# Usage: capped-run.sh <cap, e.g. 6G> -- <command> [args...]
set -u
if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
  echo "usage: capped-run.sh <cap, e.g. 6G> -- <command> [args...]" >&2
  exit 2
fi
cap=$1
shift 2
if ! command -v systemd-run >/dev/null 2>&1; then
  echo "capped-run.sh: systemd-run not found; refusing to run the suite uncapped" >&2
  exit 127
fi
exec systemd-run --user --wait --collect --pipe \
  -p "MemoryMax=$cap" -p MemorySwapMax=0 \
  -p "WorkingDirectory=$PWD" -E "PATH=$PATH" -E "HOME=$HOME" \
  "$@"
