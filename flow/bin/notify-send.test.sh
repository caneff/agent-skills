#!/usr/bin/env bash
# Regression test for the shift-2 hang (#1017): a value-taking flag as the
# final argument left `shift 2` with only one argument to consume, so it
# shifted nothing and the parse loop spun forever. Each such flag is run
# alone, last, under a timeout — a timeout exit (124) is the hang, and any
# exit other than a clean 0 fails the case: a run that never actually
# exercised the parser (a refused namespace, a failed bind) must not read
# as the same PASS a real, completed run gets (docs/agents/defect-
# classes.md class 1).
#
# The real toast send (wscript.exe, hardcoded by absolute path so PATH
# stubbing can't intercept it) is isolated with a mount-namespace bind
# mount, so a green run never pops a real Windows toast. A failed bind
# fails the case loud (exit 97, surfaced as a FAIL) instead of silently
# falling through to the real binary.
#
# The flag list below is checked against the parser's own case arm, so a
# flag added to one side and not the other is caught rather than silently
# left untested.
# Run this file directly with bash from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/notify-send"
fails=0

# `command -v unshare` only proves the binary exists, not that unprivileged
# user namespaces are usable — on a host where they're refused this probe
# must fail the same way the real thing would, or the skip guard reports a
# false capability check when there is nothing to run against.
if ! unshare -rm true 2>/dev/null; then
  echo "SKIP notify-send.test.sh: unshare -rm not usable here (unprivileged user namespaces refused) to isolate wscript.exe" >&2
  exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
stub="$tmp/wscript.exe"
printf '#!/usr/bin/env bash\nexit 0\n' > "$stub"
chmod +x "$stub"

# value-taking flags, short and long, exactly as the parser's case arm lists them
flags=(-a --app-name -i --icon -u --urgency -t --expire-time -c --category -h --hint -A --action -r --replace-id)

case_arm=$(grep -m1 -F -- '-a|--app-name|-i|--icon' "$script")
if [ -z "$case_arm" ]; then
  echo "FAIL notify-send.test.sh could not find the value-flag case arm in $script to check the flag list against"
  fails=1
else
  from_script=$(printf '%s' "$case_arm" | sed 's/).*//' | tr '|' '\n' | sed 's/^[[:space:]]*//' | sort)
  from_test=$(printf '%s\n' "${flags[@]}" | sort)
  if [ "$from_script" = "$from_test" ]; then
    echo "PASS the test's flag list matches the parser's case arm exactly"
  else
    echo "FAIL the test's flag list has drifted from the parser's case arm:"
    diff <(printf '%s\n' "$from_script") <(printf '%s\n' "$from_test") | sed 's/^/  /'
    fails=1
  fi
fi

for flag in "${flags[@]}"; do
  out=$(unshare -rm bash -c '
    mount --bind "$1" /mnt/c/Windows/System32/wscript.exe || {
      echo "bind mount for the wscript.exe stub failed" >&2; exit 97
    }
    exec env HERDR_TOAST_PANE=test-pane timeout 5 bash "$2" "$3"
  ' _ "$stub" "$script" "$flag" 2>&1)
  rc=$?
  case "$rc" in
    124) echo "FAIL '$flag' as the last argument hangs (timed out): $out"; fails=1 ;;
    0)   echo "PASS '$flag' as the last argument does not hang (rc=0)" ;;
    97)  echo "FAIL '$flag' as the last argument: isolation setup failed, not a real run: $out"; fails=1 ;;
    *)   echo "FAIL '$flag' as the last argument exited $rc unexpectedly: $out"; fails=1 ;;
  esac
done

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
