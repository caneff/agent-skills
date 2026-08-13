#!/usr/bin/env bash
# Sync Windows VS Code user settings.json <-> this repo copy. The live file is on
# the Windows side of WSL (no symlink holds across), so this is the one command
# that keeps the snapshot fresh — or restores it onto a machine.
#
#   sync.sh            repo  <- live   (default: refresh the backup, then commit)
#   sync.sh --restore  live  <- repo   (write the backup onto this machine)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$here/settings.json"

# Locate the live Windows settings.json without hardcoding the Windows username.
live=$(ls /mnt/c/Users/*/AppData/Roaming/Code/User/settings.json 2>/dev/null | head -1)
[ -n "$live" ] || { echo "no Windows VS Code settings.json under /mnt/c/Users/*/AppData/Roaming/Code/User/" >&2; exit 1; }

if [ "${1:-}" = "--restore" ]; then
  cp "$repo" "$live" && echo "restored: $live <- $repo"
else
  cp "$live" "$repo" && echo "backed up: $repo <- $live  (commit to save)"
fi
