#!/usr/bin/env bash
# Regression test for the shift-2 hang (#1017): a value-taking flag as the
# final argument left `shift 2` with only one argument to consume, so it
# shifted nothing and the parse loop spun forever. Each such flag is run
# alone, last, under a timeout — a timeout exit (124) is the hang.
#
# The real toast send (wscript.exe, hardcoded by absolute path so PATH
# stubbing can't intercept it) is isolated with a mount-namespace bind
# mount, so a green run never pops a real Windows toast. HERDR_TOAST_PANE
# is set so the herdr-pane lookup never runs either.
# Run this file directly with bash from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/notify-send"
fails=0

if ! command -v unshare >/dev/null 2>&1; then
  echo "SKIP notify-send.test.sh: unshare not available to isolate wscript.exe" >&2
  exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
stub="$tmp/wscript.exe"
printf '#!/usr/bin/env bash\nexit 0\n' > "$stub"
chmod +x "$stub"

# value-taking flags, short and long, exactly as the parser's case arm lists them
flags=(-a --app-name -i --icon -u --urgency -t --expire-time -c --category -h --hint -A --action -r --replace-id)

for flag in "${flags[@]}"; do
  out=$(unshare -rm bash -c '
    mount --bind "$1" /mnt/c/Windows/System32/wscript.exe 2>/dev/null
    exec env HOME="$2" HERDR_TOAST_PANE=test-pane timeout 5 bash "$3" "$4"
  ' _ "$stub" "$tmp/home" "$script" "$flag" 2>&1)
  rc=$?
  if [ "$rc" -eq 124 ]; then
    echo "FAIL '$flag' as the last argument hangs (timed out): $out"; fails=1
  else
    echo "PASS '$flag' as the last argument does not hang (rc=$rc)"
  fi
done

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
