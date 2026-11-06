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
# A systemd user unit starts in the manager's environment, not ours: pass through
# PATH, HOME, NODE_OPTIONS and every CRAP_* variable by name, or the preload never
# loads and the suite passes uninstrumented (-E NAME copies the caller's value).
envargs=()
for v in PATH HOME NODE_OPTIONS $(compgen -e | grep '^CRAP_'); do
  [ -n "${!v+x}" ] && envargs+=(-E "$v")
done
exec systemd-run --user --wait --collect --pipe \
  -p "MemoryMax=$cap" -p MemorySwapMax=0 -p "WorkingDirectory=$PWD" \
  "${envargs[@]}" "$@"
