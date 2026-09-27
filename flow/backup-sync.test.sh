#!/usr/bin/env bash
# Contract test for backup-sync.sh (#1031): claude/settings.json moved off
# the copy-only manifest (install.sh symlinks it now), so --restore must not
# touch it at all — a plain cp over an existing symlink's target would
# silently overwrite content the harness may have written since.
# Run: bash flow/backup-sync.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0

if grep -q '"claude/settings.json"' "$here/backup-sync.sh"; then
  echo "FAIL claude/settings.json is still in backup-sync.sh's COPIES manifest"; fails=1
else
  echo "PASS claude/settings.json is not in backup-sync.sh's COPIES manifest"
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home/.claude"
printf 'SENTINEL\n' > "$tmp/home/.claude/settings-target.json"
ln -s "$tmp/home/.claude/settings-target.json" "$tmp/home/.claude/settings.json"

out=$(HOME="$tmp/home" bash "$here/backup-sync.sh" --restore 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then
  echo "PASS backup-sync.sh --restore exits 0 with a symlinked settings.json in place"
else
  echo "FAIL backup-sync.sh --restore exited $rc: $out"; fails=1
fi
if [ -L "$tmp/home/.claude/settings.json" ] \
   && [ "$(readlink "$tmp/home/.claude/settings.json")" = "$tmp/home/.claude/settings-target.json" ] \
   && [ "$(cat "$tmp/home/.claude/settings-target.json")" = SENTINEL ]; then
  echo "PASS --restore leaves the settings.json symlink and its content intact"
else
  echo "FAIL --restore touched settings.json: $(ls -la "$tmp/home/.claude/settings.json" 2>&1) $(cat "$tmp/home/.claude/settings-target.json" 2>&1)"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
