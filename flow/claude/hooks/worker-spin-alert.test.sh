#!/usr/bin/env bash
# Contract test for worker-spin-alert.sh (#925): the classifier against
# transcript fixtures, then the PostToolUse hook against a stubbed herdr.
# Run: bash flow/claude/hooks/worker-spin-alert.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/worker-spin-alert.sh"
fx="$here/fixtures/spin"
fails=0

# classify <fixture> -> JSON on stdout
classify() { bash "$hook" --classify "$fx/$1" 2>/dev/null; }
expect() { # <label> <fixture> <jq -e filter>
  if classify "$2" | jq -e "$3" >/dev/null 2>&1; then echo "PASS: $1"
  else echo "FAIL: $1 — got: $(classify "$2")"; fails=1; fi
}

expect "a real spin (a 180-call echo ok loop) is flagged with tool, input and count" real-spin.jsonl \
  '.spinning == true and .tool == "Bash" and .input.command == "echo ok" and .count >= 20'
expect "varied work is never flagged" varied.jsonl '.spinning == false'
expect "a bounded retry below the threshold is not flagged" bounded-retry.jsonl '.spinning == false'
expect "a single repeated call is not flagged" single-call.jsonl '.spinning == false and .count == 1'
expect "a different tool between two runs breaks the run" interrupted.jsonl '.spinning == false and .count == 15'

# The hook: a spinning worker alerts the controller once; a varied one never.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/home/.claude/sessions"
cat > "$tmp/bin/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") echo '{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}}]}}' ;;
  "agent get") echo '{"result":{"agent":{"name":"skills-893"}}}' ;;
  "agent prompt") printf '%s' "\$4" >> "$tmp/prompts" ;;
esac
STUB
chmod +x "$tmp/bin/herdr"
stat=$(cat /proc/$$/stat); start=$(set -- ${stat##*) }; echo "${20}")
printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-dc"}\n' "$$" "$start" > "$tmp/home/.claude/sessions/$$.json"
fire() { printf '{"session_id":"s1","transcript_path":"%s"}' "$fx/$1" | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook"; echo $?; }

rc=$(fire real-spin.jsonl); fire real-spin.jsonl >/dev/null
if [ "$rc" = 0 ] && [ "$(grep -c 'worker-spin-alert' "$tmp/prompts")" = 1 ] \
   && grep -Eq '#893.*Bash.*echo ok.*at least [0-9]+ times' "$tmp/prompts"; then
  echo "PASS: a spin alerts the controller once, naming worker, tool, input and count"
else echo "FAIL: spin alert — rc=$rc prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi
rm -f "$tmp/prompts"
rc=$(fire varied.jsonl); [ "$rc" = 0 ] && [ ! -e "$tmp/prompts" ] && echo "PASS: varied work sends no alert" || { echo "FAIL: varied work alerted"; fails=1; }

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
