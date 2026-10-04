#!/usr/bin/env bash
# Contract test for settings-lint.sh (#1225): one settings file per case.
# Run: bash flow/settings-lint.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lint="$here/settings-lint.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0
# case_ <name> <want-exit> <needle> <json>
case_() {
  local name=$1 want=$2 needle=$3 f="$tmp/settings.json" out rc
  printf '%s' "$4" > "$f"
  out=$(bash "$lint" "$f" 2>&1); rc=$?
  if [ "$rc" != "$want" ]; then echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return; fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then echo "FAIL: $name — output missing '$needle'"; echo "  out: $out"; fails=1; return; fi
  echo "PASS: $name"
}

case_ "top-level autoMode with \$defaults passes" 0 "" \
  '{"autoMode":{"allow":["$defaults","x"],"environment":["$defaults"]}}'
case_ "no autoMode at all passes" 0 "" '{"permissions":{"allow":[]}}'
case_ "autoMode under permissions fails" 1 "permissions.autoMode" \
  '{"permissions":{"autoMode":{"allow":["$defaults"]}}}'
case_ "allow list without \$defaults fails" 1 "autoMode.allow" \
  '{"autoMode":{"allow":["only this"]}}'
case_ "environment list without \$defaults fails" 1 "autoMode.environment" \
  '{"autoMode":{"environment":["only this"]}}'
case_ "soft_deny is owned: no \$defaults is allowed" 0 "" \
  '{"autoMode":{"soft_deny":["spelled out"]}}'
case_ "autoMode that is a string fails" 1 "autoMode must be an object" '{"autoMode":"oops"}'
case_ "autoMode that is an array fails" 1 "autoMode must be an object" '{"autoMode":[1]}'
case_ "a list that is a string fails" 1 "autoMode.allow must be an array" '{"autoMode":{"allow":"only this"}}'
case_ "a list holding a non-string still lints" 1 "autoMode.allow" '{"autoMode":{"allow":[1]}}'
case_ "invalid JSON fails" 1 "not valid JSON" '{"autoMode":'
case_ "an empty file is not a pass" 1 "not valid JSON" ""
printf '{}' > "$tmp/ok.json"
out=$(PATH=/nonexistent /bin/bash "$lint" "$tmp/ok.json" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"jq is not installed"* ]]; then echo "PASS: no jq is exit 2 naming jq"
else echo "FAIL: no jq — want exit 2 naming jq, got $rc: $out"; fails=1; fi
out=$(bash "$lint" "$tmp/nope.json" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"cannot read"* ]]; then echo "PASS: missing file fails"
else echo "FAIL: missing file — got $rc: $out"; fails=1; fi
out=$(bash "$lint" "$here/claude/settings.json" 2>&1); rc=$?
if [ "$rc" = 0 ]; then echo "PASS: this repo's settings.json is clean"
else echo "FAIL: this repo's settings.json — $out"; fails=1; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
