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
expect "run_id is the tool-use id of the streak's first call" real-spin.jsonl '.run_id == "e1"'
expect "varied work is never flagged" varied.jsonl '.spinning == false'
expect "a bounded retry below the threshold is not flagged" bounded-retry.jsonl '.spinning == false'
expect "a single repeated call is not flagged" single-call.jsonl '.spinning == false and .count == 1'
expect "a different tool between two runs breaks the run" interrupted.jsonl '.spinning == false and .count == 15'
expect "run_id resets to the second run's own first call" interrupted.jsonl '.run_id == "z1"'
expect "a streak that fills the whole read window has a null run_id, not a window-relative one" window-501.jsonl \
  '.spinning == true and .count == 500 and .run_id == null'

# The byte cap can hide the boundary before the line cap does — a spin on
# large inputs (a Write, an Edit, a heredoc) can exhaust it in well under
# $WINDOW calls. byte-cap-40/41.jsonl each have a real `Read` boundary at
# the transcript's start, only visible under a shrunk SPIN_BYTE_CAP.
byte_cap_classify() { SPIN_BYTE_CAP=3200 bash "$hook" --classify "$fx/$1" 2>/dev/null; }
if byte_cap_classify byte-cap-40.jsonl | jq -e '.spinning == true and .run_id == null' >/dev/null 2>&1; then
  echo "PASS: a boundary hidden by the byte cap alone (not the line cap) gives a null run_id"
else echo "FAIL: byte-cap boundary — got: $(byte_cap_classify byte-cap-40.jsonl)"; fails=1; fi

expect "a tool_use with no id degrades to a null run_id, not a crash or a wrong id" no-id-spin.jsonl \
  '.spinning == true and .run_id == null'

# The hook: a spinning worker alerts the controller once; a varied one never.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/home/.claude/sessions"
cat > "$tmp/bin/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") echo '{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}}]}}' ;;
  "agent get") echo '{"result":{"agent":{"name":"skills-893"}}}' ;;
  "agent prompt") printf '%s\n' "\$4" >> "$tmp/prompts" ;;
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

# A real transcript pads every call with ~8 lines and, mid-spin, subagent
# sidechain calls; neither may hide a spin (C1, C3). Built here, not committed.
pad="$tmp/padded.jsonl"
{ head -n 1 "$fx/real-spin.jsonl"
  for i in $(seq 1 100); do
    printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"p%s","name":"Bash","input":{"command":"echo ok"}}]}}\n' "$i"
    printf '{"type":"assistant","isSidechain":true,"message":{"role":"assistant","content":[{"type":"tool_use","id":"sc%s","name":"Read","input":{"file_path":"/x"}}]}}\n' "$i"
    for j in 1 2 3 4 5 6; do printf '{"type":"attachment","attachment":{"n":%s}}\n' "$j"; done
  done; } > "$pad"
if bash "$hook" --classify "$pad" | jq -e '.spinning == true and .count == 100' >/dev/null; then
  echo "PASS: padding lines and sidechain calls do not hide a spin"
else echo "FAIL: padded spin — got: $(bash "$hook" --classify "$pad")"; fails=1; fi

if bash "$hook" --classify /nonexistent/t.jsonl >/dev/null 2>&1; then
  echo "FAIL: --classify on an unreadable path answered instead of refusing"; fails=1
else echo "PASS: --classify refuses an unreadable transcript"; fi

# A spinning session with no worker brief is not a worker: no alert.
nb="$tmp/nobrief.jsonl"; tail -n +2 "$fx/real-spin.jsonl" > "$nb"
rm -f "$tmp/prompts"
printf '{"session_id":"s2","transcript_path":"%s"}' "$nb" | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook"; rc=$?
[ "$rc" = 0 ] && [ ! -e "$tmp/prompts" ] && ! grep -q s2 "$tmp/home/.claude/worker-spin-alerts.log" 2>/dev/null \
  && echo "PASS: a spin with no worker brief sends no alert and leaves no log line" \
  || { echo "FAIL: non-worker spin — rc=$rc prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; }

# An alert that was not sent (no controller pane) is retried on the next call.
printf '{"result":{"agents":[]}}\n' > "$tmp/agents.empty"
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
cp "$tmp/bin/herdr" "$tmp/bin/herdr.real"
sed -i "s|echo '{\"result\":{\"agents\":\[.*\]}}'|cat $tmp/agents.empty|" "$tmp/bin/herdr"
fire real-spin.jsonl >/dev/null
mv "$tmp/bin/herdr.real" "$tmp/bin/herdr"
fire real-spin.jsonl >/dev/null
if grep -q 'not-sent' "$tmp/home/.claude/worker-spin-alerts.log" && [ "$(grep -c 'worker-spin-alert' "$tmp/prompts")" = 1 ]; then
  echo "PASS: a not-sent alert is retried, and sent once the controller is reachable"
else echo "FAIL: not-sent retry — log: $(cat "$tmp/home/.claude/worker-spin-alerts.log")"; fails=1; fi

# Two distinct long inputs sharing a 120-character prefix are two spins: both alert.
long="$tmp/long"; pre=$(printf 'a%.0s' $(seq 1 130))
for v in X Y; do
  { head -n 1 "$fx/real-spin.jsonl"
    for i in $(seq 1 25); do
      printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"l%s%s","name":"Bash","input":{"command":"%s%s"}}]}}\n' "$v" "$i" "$pre" "$v"
    done; } > "$long-$v.jsonl"
done
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
for v in X Y; do
  printf '{"session_id":"s3","transcript_path":"%s"}' "$long-$v.jsonl" | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook"
done
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 2 ]; then
  echo "PASS: two long same-prefix spins each alert"
else echo "FAIL: same-prefix spins — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

# A spin, a different tool call, then the same spin resumed: two streaks,
# two run_ids, two alerts — not deduped as a repeat of the first (#998).
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
printf '{"session_id":"s4","transcript_path":"%s"}' "$fx/real-spin.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
printf '{"session_id":"s4","transcript_path":"%s"}' "$fx/resumed-spin-2.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 2 ]; then
  echo "PASS: a resumed spin after a different call alerts a second time"
else echo "FAIL: resumed spin — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

# A single uninterrupted spin that outgrows the 500-call read window must
# still alert once, not once per call past the window (P1/C1): the window
# slides but run_id stays null throughout the plateau, so the dedupe key
# stays stable. window-502.jsonl is window-501.jsonl plus one more call.
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
printf '{"session_id":"s5","transcript_path":"%s"}' "$fx/window-501.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
printf '{"session_id":"s5","transcript_path":"%s"}' "$fx/window-502.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 1 ]; then
  echo "PASS: a spin that outgrows the read window still alerts only once"
else echo "FAIL: window-outgrowing spin — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

# Same plateau behavior, byte cap instead of line cap: a spin that outgrows
# SPIN_BYTE_CAP before it outgrows $WINDOW must still alert once.
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
printf '{"session_id":"s6","transcript_path":"%s"}' "$fx/byte-cap-40.jsonl" \
  | SPIN_BYTE_CAP=3200 HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
printf '{"session_id":"s6","transcript_path":"%s"}' "$fx/byte-cap-41.jsonl" \
  | SPIN_BYTE_CAP=3200 HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 1 ]; then
  echo "PASS: a spin that outgrows the byte cap alone still alerts only once"
else echo "FAIL: byte-cap-outgrowing spin — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

# A live spin's first alert carries a real run_id; if that SAME streak
# keeps growing and later crosses a cap, run_id goes null and a naive
# exact-key dedupe reads it as a different streak and re-alerts a second
# time for one still-running spin (Codex adversarial review, PR #1061).
# One alert total, not two: fire just before the cap (real id) then just
# after (null id), same session both times.
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
printf '{"session_id":"s9","transcript_path":"%s"}' "$fx/real-spin.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
printf '{"session_id":"s9","transcript_path":"%s"}' "$fx/window-501.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 1 ]; then
  echo "PASS: a live spin crossing the line cap after its first alert does not alert twice"
else echo "FAIL: line-cap-crossing spin — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
printf '{"session_id":"s10","transcript_path":"%s"}' "$fx/byte-cap-40.jsonl" \
  | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
printf '{"session_id":"s10","transcript_path":"%s"}' "$fx/byte-cap-41.jsonl" \
  | SPIN_BYTE_CAP=3200 HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$hook" >/dev/null
if [ "$(grep -c 'worker-spin-alert' "$tmp/prompts" 2>/dev/null)" = 1 ]; then
  echo "PASS: a live spin crossing the byte cap after its first alert does not alert twice"
else echo "FAIL: byte-cap-crossing spin — prompts: $(cat "$tmp/prompts" 2>/dev/null)"; fails=1; fi

# A deployment missing the sibling lib (#991's own round-1 bug) must fail
# loud, not join the "not a worker transcript" exit 0 via a bare
# command-not-found on stderr.
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
nolib="$tmp/nolib"; mkdir -p "$nolib"; cp "$hook" "$nolib/"
rc=$(printf '{"session_id":"s11","transcript_path":"%s"}' "$fx/real-spin.jsonl" \
     | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$nolib/$(basename "$hook")" >/dev/null 2>&1; echo $?)
if [ "$rc" = 0 ] && [ ! -e "$tmp/prompts" ] && grep -q $'lib-missing\tnot-sent' "$tmp/home/.claude/worker-spin-alerts.log" 2>/dev/null; then
  echo "PASS: a hook deployed without its sibling lib logs lib-missing and exits 0"
else
  echo "FAIL: a hook deployed without its sibling lib — rc $rc, log: $(cat "$tmp/home/.claude/worker-spin-alerts.log" 2>/dev/null)"; fails=1
fi

# A lib that sources cleanly but is missing a function the hook calls (mid-edit
# skew between the symlinked hook and its sibling) must be caught too — not
# just an absent file (Codex gate pass on PR #1066).
rm -f "$tmp/prompts" "$tmp/home/.claude/worker-spin-alerts.log"
partial="$tmp/partial"; mkdir -p "$partial"; cp "$hook" "$partial/"
sed '/^worker_alert_logline() {/,/^}/d' "$here/worker-alert-lib.sh" > "$partial/worker-alert-lib.sh"
rc=$(printf '{"session_id":"s12","transcript_path":"%s"}' "$fx/real-spin.jsonl" \
     | HOME="$tmp/home" PATH="$tmp/bin:$PATH" bash "$partial/$(basename "$hook")" >/dev/null 2>&1; echo $?)
if [ "$rc" = 0 ] && [ ! -e "$tmp/prompts" ] && grep -q $'lib-missing\tnot-sent.*worker_alert_logline' "$tmp/home/.claude/worker-spin-alerts.log" 2>/dev/null; then
  echo "PASS: a hook deployed with an incomplete sibling lib names the missing symbol and exits 0"
else
  echo "FAIL: incomplete lib — rc $rc, log: $(cat "$tmp/home/.claude/worker-spin-alerts.log" 2>/dev/null)"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
