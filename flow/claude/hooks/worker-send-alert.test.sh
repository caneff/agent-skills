#!/usr/bin/env bash
# Contract test for worker-send-alert.sh: a synthetic PostToolUse event
# for a SendMessage on stdin, a synthetic transcript, a scratch HOME holding
# the sessions registry, a stubbed `herdr` on PATH and a fake controller inbox
# socket -> exactly one peer-message frame on that socket (#1946) when the send
# to the controller came back failed, or none, and never a `herdr agent
# prompt`. Runs offline; no real session is touched.
# Run: bash flow/claude/hooks/worker-send-alert.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/worker-send-alert.sh"

tmp=$(mktemp -d)
. "$here/worker-alert-testlib.sh"
trap 'kill_inboxes; rm -rf "$tmp"' EXIT

stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") cat "$tmp/agent-list.json" ;;
  "agent get") printf '{"result":{"agent":{"name":"skills-1540","pane_id":"%s"}}}\n' "\$3" ;;
  "agent prompt") echo "\$*" >> "$tmp/prompt.called" ;;
esac
STUB
chmod +x "$stubdir/herdr"

home="$tmp/home"
mkdir -p "$home/.claude/sessions"
proc_start() { local stat; stat=$(cat "/proc/$1/stat") && (set -- ${stat##*) }; echo "${20}"); }
wa_start_inbox "$tmp/inbox" ctl; inbox="$tmp/inbox"; ctl_sock="$wa_sock"
wa_key "$home/.claude/sessions" "$$"
printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-b6","messagingSocketPath":"%s"}\n' "$$" "$(proc_start $$)" "$ctl_sock" > "$home/.claude/sessions/$$.json"
agents_ok='{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}}]}}'
printf '%s\n' "$agents_ok" > "$tmp/agent-list.json"
log="$home/.claude/worker-send-alerts.log"

brief='<command-message>implement</command-message>\n<command-name>/implement</command-name>\n<command-args>1540 --tier heavy --controller \"skills-b6\"</command-args>'
human() { printf '{"type":"user","origin":{"kind":"human"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
transcript="$tmp/t.jsonl"; human "$brief" > "$transcript"
other="$tmp/other.jsonl"; human 'just a chat' > "$other"
drain="$tmp/drain.jsonl"; human "${brief//skills-b6/drain}" > "$drain"

fails=0
# run <name> <transcript> <event-json> [env...] -> sets $got (a new frame
# reached the controller's inbox), $text (its alert) and $count (frames)
sent_lines() { local c; c=$(grep -c $'\tsent\t' "$log" 2>/dev/null); echo "${c:-0}"; }
run() {
  local name=$1 t=$2 event=$3 out rc before; shift 3
  rm -f "$inbox"/frames/[0-9]* "$tmp/prompt.called"; before=$(sent_lines)
  out=$(jq -c --arg t "$t" '. + {transcript_path:$t, session_id:"w"}' <<<"$event" \
        | env HOME="$home" HERDR_PANE_ID="w2W:p1" PATH="$stubdir:$PATH" "$@" bash "$hook" 2>&1)
  rc=$?
  got="" text="" count=0
  if [ "$(sent_lines)" -gt "$before" ] && wa_wait_frame "$inbox"; then got=yes; text=$(wa_text "$inbox"); count=$(wa_frames "$inbox"); fi
  [ ! -e "$tmp/prompt.called" ] || { echo "FAIL: $name — the herdr prompt call called: $(cat "$tmp/prompt.called")"; fails=1; }
  [ "$rc" = 0 ] || { echo "FAIL: $name — want exit 0, got $rc"; echo "  out: $out"; fails=1; }
  last_out=$out
}
# send_event <tool_use_id> <to> <response-json> [tool_name]
send_event() { jq -nc --arg id "$1" --arg to "$2" --argjson r "$3" --arg tool "${4:-SendMessage}" \
  '{hook_event_name:"PostToolUse",tool_name:$tool,tool_use_id:$id,tool_input:{to:$to,message:"PR up"},tool_response:$r}'; }
failed='{"success":false,"message":"No agent named '"'"'x'"'"' is reachable.\nUse ListAgents."}'
delivered='{"success":true,"message":"sent"}'
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; echo "  got: $got text: $text count: $count hook output: $last_out"; fails=1; }
expect_alert() {
  if [ "$got" = yes ] && [ "$count" = 1 ] && grep -q "worker #1540" <<<"$text" \
     && grep -q "failed" <<<"$text" && grep -q "skills-1540" <<<"$text" && grep -q "No agent named" <<<"$text"; then pass "$1"; else fail "$1 — want one alert on the controller socket"; fi
}
expect_none() { [ -z "$got" ] && [ "$count" = 0 ] && pass "$1" || fail "$1 — want no alert"; }
reset_log() { rm -f "$log"; }

reset_log
run "failed send to session name" "$transcript" "$(send_event tu-1 skills-b6 "$failed")"
expect_alert "a failed send to the controller's session name alerts its socket at once"

reset_log
run "delivered send" "$transcript" "$(send_event tu-2 skills-b6 "$delivered")"
expect_none "a delivered send does not alert"

reset_log
run "failed send to socket address" "$transcript" "$(send_event tu-3 "uds:$ctl_sock" "$failed")"
expect_alert "a failed send to the controller's socket address alerts"

reset_log
run "failed send to a subagent" "$transcript" "$(send_event tu-4 "some-subagent" "$failed")"
expect_none "a failed send to someone other than the controller does not alert"

reset_log
run "no brief" "$other" "$(send_event tu-5 skills-b6 "$failed")"
expect_none "a failed send from a session with no /implement brief does not alert"

reset_log
run "other tool" "$transcript" "$(send_event tu-6 skills-b6 "$failed" Bash)"
expect_none "a tool other than SendMessage does not alert"

reset_log
run "drain controller" "$drain" "$(send_event tu-7 drain "$failed")"
# Not just no alert: the guard exits before any log line, where the no-pane
# fallback would also send nothing and log "not-sent".
if [ -z "$got" ] && [ ! -s "$log" ]; then pass "the controller named drain is no session: no alert and no log line"; else fail "drain — log: $(cat "$log" 2>/dev/null)"; fi

reset_log
run "dedupe" "$transcript" "$(send_event tu-8 skills-b6 "$failed")"
run "dedupe" "$transcript" "$(send_event tu-8 skills-b6 "$failed")"
[ "$count" = 0 ] && [ "$(grep -c $'\tsent\t' "$log")" = 1 ] && pass "the same failed send firing twice alerts once" || fail "dedupe — log: $(cat "$log")"

reset_log
noid() { jq -c 'del(.tool_use_id)' <<<"$(send_event x skills-b6 "$failed")" | jq -c --arg m "$1" '.tool_input.message = $m'; }
run "no id, first" "$transcript" "$(noid 'PR up')"
run "no id, second message" "$transcript" "$(noid 'a question')"
n_sent=$(grep -c $'\tsent\t' "$log")
run "no id, repeat of the second" "$transcript" "$(noid 'a question')"
if [ "$n_sent" = 2 ] && [ "$(grep -c $'\tsent\t' "$log")" = 2 ]; then pass "sends with no tool_use_id alert once each, never silenced by an earlier one"; else fail "no tool_use_id — log: $(cat "$log" 2>/dev/null)"; fi

reset_log
run "error string" "$transcript" "$(send_event tu-9 skills-b6 '"Error: No agent named x is reachable"')"
expect_alert "a failure reported as an error string alerts too"

reset_log
sleep 60 & new_pid=$!; trap 'kill $new_pid 2>/dev/null; kill_inboxes; rm -rf "$tmp"' EXIT
wa_start_inbox "$tmp/inbox2" new; new_inbox="$tmp/inbox2"
wa_key "$home/.claude/sessions" "$new_pid"
printf '{"pid":%s,"procStart":"%s","sessionId":"new-session","name":"skills-new","messagingSocketPath":"%s"}\n' "$new_pid" "$(proc_start $new_pid)" "$wa_sock" > "$home/.claude/sessions/$new_pid.json"
printf '{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}},{"pane_id":"w8:p2","agent_session":{"value":"new-session"}}]}}\n' > "$tmp/agent-list.json"
adopted="$tmp/adopted.jsonl"; { cat "$transcript"; printf '{"type":"user","isMeta":true,"origin":{"kind":"peer","name":"skills-new"},"message":{"role":"user","content":"<cross-session-message from=\\"skills-new\\">Your controller is now skills-new</cross-session-message>"}}\n'; } > "$adopted"
run "after adoption" "$adopted" "$(send_event tu-14 skills-new "$failed")"
if [ "$(wa_frames "$new_inbox")" = 1 ] && [ "$count" = 0 ]; then pass "a failed send after a controller hand-off alerts the new controller's socket, not the old one"; else fail "adoption — want one frame on the new inbox; log: $(cat "$log" 2>/dev/null); sessions: $(ls "$home/.claude/sessions")"; fi
run "before adoption name" "$transcript" "$(send_event tu-15 skills-new "$failed")"
expect_none "a failed send to another live session is no controller send without a hand-off"
printf '%s\n' "$agents_ok" > "$tmp/agent-list.json"; rm -f "$home/.claude/sessions/$new_pid.json" "$home/.claude/sessions/$new_pid".*.key

reset_log
run "no tool_response" "$transcript" "$(jq -c 'del(.tool_response)' <<<"$(send_event tu-10 skills-b6 "$delivered")")"
if [ -z "$got" ] && grep -q 'no tool_response' "$log"; then pass "an event with no tool_response alerts nobody and is logged"; else fail "absent tool_response — log: $(cat "$log" 2>/dev/null)"; fi

reset_log
mv "$home/.claude/sessions/$$.json" "$tmp/record.bak"
run "no session record" "$transcript" "$(send_event tu-11 skills-b6 "$failed")"
if [ -z "$got" ] && grep -q 'not-sent.*no live session record' "$log"; then pass "no session record for the controller is logged not-sent"; else fail "no record — log: $(cat "$log" 2>/dev/null)"; fi
mv "$tmp/record.bak" "$home/.claude/sessions/$$.json"

reset_log
mv "$home/.claude/sessions/$$".*.key "$tmp/key.bak"
run "no key file" "$transcript" "$(send_event tu-12 skills-b6 "$failed")"
if [ -z "$got" ] && grep -q 'not-sent.*no key file' "$log"; then pass "a controller with no key file is logged not-sent naming the cause"; else fail "no key — log: $(cat "$log" 2>/dev/null)"; fi
wa_key "$home/.claude/sessions" "$$"; rm -f "$tmp/key.bak"

reset_log
mkdir -p "$tmp/nolib" && cp "$hook" "$tmp/nolib/"
out=$(jq -c --arg t "$transcript" '. + {transcript_path:$t}' <<<"$(send_event tu-13 skills-b6 "$failed")" \
      | HOME="$home" PATH="$stubdir:$PATH" bash "$tmp/nolib/worker-send-alert.sh" 2>&1); rc=$?
if [ "$rc" = 0 ] && grep -q 'lib-missing' "$log"; then pass "a hook with no sibling lib logs lib-missing and exits 0"; else fail "lib-missing — rc $rc log: $(cat "$log" 2>/dev/null) out: $out"; fi

reset_log
partial="$tmp/partial-deliver"; mkdir -p "$partial"; cp "$hook" "$partial/"
sed '/^worker_alert_deliver() {/,/^}/d' "$here/worker-alert-lib.sh" > "$partial/worker-alert-lib.sh"
out=$(jq -c --arg t "$transcript" '. + {transcript_path:$t}' <<<"$(send_event tu-14 skills-b6 "$failed")" \
      | HOME="$home" PATH="$stubdir:$PATH" bash "$partial/worker-send-alert.sh" 2>&1); rc=$?
if [ "$rc" = 0 ] && grep -q $'lib-missing\tnot-sent.*worker_alert_deliver' "$log"; then pass "a lib without worker_alert_deliver is named as the missing symbol"; else fail "lib without deliver — rc $rc log: $(cat "$log" 2>/dev/null) out: $out"; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
