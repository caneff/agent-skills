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
case_ "invalid JSON fails" 1 "not valid JSON" '{"autoMode":'
case_ "an empty file is not a pass" 1 "not valid JSON" ""
out=$(bash "$lint" "$tmp/nope.json" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"cannot read"* ]]; then echo "PASS: missing file fails"
else echo "FAIL: missing file — got $rc: $out"; fails=1; fi
out=$(bash "$lint" "$here/claude/settings.json" 2>&1); rc=$?
if [ "$rc" = 0 ]; then echo "PASS: this repo's settings.json is clean"
else echo "FAIL: this repo's settings.json — $out"; fails=1; fi

# The live e2e lock (#1392): each way an agent starts twitch-rules-scroller's
# ./e2e.sh is an `ask` rule, since it takes over Chris's monitor. A rule that
# no start form matches does not stop it, so the forms are named here.
ask=$(jq -r '.permissions.ask[]?' "$here/claude/settings.json")
for rule in 'Bash(./e2e.sh *)' 'Bash(bash e2e.sh *)' 'Bash(bash ./e2e.sh *)' \
            'Bash(/home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(bash /home/caneff/src/twitch-rules-scroller/e2e.sh *)' \
            'Bash(*/.claude/worktrees/*/e2e.sh *)' 'Bash(bash */.claude/worktrees/*/e2e.sh *)'; do
  if grep -qxF -- "$rule" <<<"$ask"; then echo "PASS: ask rule $rule"
  else echo "FAIL: settings.json has no permissions.ask rule $rule"; fails=1; fi
done

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
