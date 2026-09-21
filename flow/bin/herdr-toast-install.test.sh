#!/usr/bin/env bash
# Fixture test for herdr-toast-install: a mktemp $HOME, registry step skipped,
# so the real ~/.local/bin and registry are never touched. Run from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/herdr-toast-install"
fails=0
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
names="notify-send run-hidden.vbs herdr-focus.vbs herdr-focus-pick.ps1 herdr-focus-latest"

mkdir -p "$tmp/home/.local/bin"
for n in $names; do echo old > "$tmp/home/.local/bin/$n"; done
echo keep > "$tmp/home/.local/bin/notify-send.bak-x"

HOME="$tmp/home" HERDR_TOAST_SKIP_REGISTRY=1 bash "$script" >/dev/null 2>&1 || { echo "FAIL: installer exited non-zero"; fails=1; }
for n in $names; do
  [ "$(readlink "$tmp/home/.local/bin/$n")" = "$here/$n" ] || { echo "FAIL: $n is not a symlink to flow/bin"; fails=1; }
  [ -e "$tmp/home/.local/bin/$n" ] || { echo "FAIL: $n dangles"; fails=1; }
done
[ "$(cat "$tmp/home/.local/bin/notify-send.bak-x")" = keep ] || { echo "FAIL: .bak file touched"; fails=1; }
# a Windows-read script must not name a ~/.local/bin UNC path (Windows cannot follow the symlink)
if grep -l 'wsl.localhost.*\.local' "$here"/notify-send "$here"/herdr-focus.vbs >/dev/null; then echo "FAIL: UNC path into .local/bin"; fails=1; fi
[ $fails = 0 ] && echo "ok"
exit $fails
