#!/usr/bin/env bash
# Regression test for the shift-2 hang (#1017): a value-taking flag as the
# final argument left `shift 2` with only one argument to consume, so it
# shifted nothing and the parse loop spun forever. Each such flag is run
# alone, last, under a timeout — a timeout exit (124) is the hang, and any
# exit other than a clean 0 fails the case: a run that never actually
# reached the end of the parser must not read as the same PASS a real,
# completed run gets (docs/agents/defect-classes.md class 1).
#
# The real toast send is redirected at a no-op stub via NOTIFY_SEND_WSCRIPT
# (a seam the shim exposes for exactly this), so this test runs everywhere
# with no capability probe and no skip path — a run that never really
# exercised the parser must not be able to report green by declining to run
# at all, which a namespace-isolation skip could.
#
# The flag list below is checked against the parser's own case arm, so a
# flag added to one side and not the other is caught rather than silently
# left untested.
# Run this file directly with bash from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/notify-send"
fails=0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
stub="$tmp/wscript-stub.sh"
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
  out=$(NOTIFY_SEND_WSCRIPT="$stub" HERDR_TOAST_PANE=test-pane timeout 5 bash "$script" "$flag" 2>&1)
  rc=$?
  case "$rc" in
    124) echo "FAIL '$flag' as the last argument hangs (timed out): $out"; fails=1 ;;
    0)   echo "PASS '$flag' as the last argument does not hang (rc=0)" ;;
    *)   echo "FAIL '$flag' as the last argument exited $rc unexpectedly: $out"; fails=1 ;;
  esac
done

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
