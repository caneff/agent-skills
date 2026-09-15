#!/usr/bin/env bash
# Contract test for worker-stop-alert.sh: a synthetic Stop event on stdin, a
# synthetic transcript, a scratch HOME holding the sessions registry, and a
# stubbed `herdr` on PATH -> exactly one `herdr agent prompt` to the
# controller's pane, or none. Runs offline; no real session is touched.
# Run: bash flow/claude/hooks/worker-stop-alert.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/worker-stop-alert.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# herdr stub: `agent list` names the controller's pane by its session id,
# `agent get` names the worker's agent, `agent prompt` records its argv.
stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") cat "$tmp/agent-list.json" ;;
  "agent get") printf '{"result":{"agent":{"name":"skills-820","pane_id":"%s"}}}\n' "\$3" ;;
  "agent prompt") printf '%s\n' "\$@" >> "$tmp/prompt.args"; exit "\${HERDR_PROMPT_RC:-0}" ;;
esac
STUB
chmod +x "$stubdir/herdr"

home="$tmp/home"
mkdir -p "$home/.claude/sessions"
# The controller session is this test's own shell: a live pid.
printf '{"pid":%s,"sessionId":"ctl-session","name":"skills-b6"}\n' "$$" > "$home/.claude/sessions/$$.json"
printf '{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}}]}}\n' > "$tmp/agent-list.json"

brief='<command-message>implement</command-message>\n<command-name>/implement</command-name>\n<command-args>820 --tier heavy --controller \"skills-b6\"</command-args>'

# Transcript lines.
human() { printf '{"type":"user","origin":{"kind":"human"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
assistant_text() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"%s"}]}}\n' "$1"; }

fails=0
# run <name> <transcript-file> -> sets $prompt (recorded argv, empty if none)
run() {
  local name=$1 transcript=$2 out rc
  rm -f "$tmp/prompt.args"
  out=$(jq -n --arg t "$transcript" '{hook_event_name:"Stop",session_id:"w",transcript_path:$t,stop_hook_active:false}' \
        | HOME="$home" HERDR_PANE_ID="w2W:p1" PATH="$stubdir:$PATH" bash "$hook" 2>&1)
  rc=$?
  prompt=$(cat "$tmp/prompt.args" 2>/dev/null || true)
  if [ "$rc" != 0 ]; then
    echo "FAIL: $name — want exit 0, got $rc"; echo "  out: $out"; fails=1
  fi
}
expect_alert() {
  local name=$1
  if printf '%s' "$prompt" | grep -qx 'w9:p1' \
     && printf '%s' "$prompt" | grep -q 'worker #820 stopped without reporting' \
     && printf '%s' "$prompt" | grep -q 'skills-820'; then
    echo "PASS: $name"
  else
    echo "FAIL: $name — want an alert prompt to w9:p1"; echo "  prompt: $prompt"; fails=1
  fi
}

expect_none() {
  local name=$1
  if [ -z "$prompt" ]; then echo "PASS: $name"; else echo "FAIL: $name — want no prompt"; echo "  prompt: $prompt"; fails=1; fi
}
log="$home/.claude/worker-stop-alerts.log"
reset_log() { rm -f "$log"; }

# A worker whose turn ended with no report alerts the controller.
reset_log
t="$tmp/no-report.jsonl"
{ human "$brief"; assistant_text "done, report in my pane"; } > "$t"
run "no report" "$t"
expect_alert "worker that never reported alerts the controller's pane"
if [ "$(printf '%s\n' "$prompt" | tail -n1 | wc -l)" = 1 ] && ! printf '%s' "$prompt" | grep -q '^! '; then
  echo "PASS: alert is one line with no \`! \` command"
else
  echo "FAIL: alert text is not one plain line"; fails=1
fi

# A turn already alerted is not alerted again when the stop is re-evaluated.
run "same turn again" "$t"
expect_none "a re-evaluated stop of an already-alerted turn does not re-fire"

# stop_hook_active: the harness is re-running Stop hooks for this stop.
reset_log
rm -f "$tmp/prompt.args"
jq -n --arg t "$t" '{hook_event_name:"Stop",session_id:"w",transcript_path:$t,stop_hook_active:true}' \
  | HOME="$home" HERDR_PANE_ID="w2W:p1" PATH="$stubdir:$PATH" bash "$hook" >/dev/null 2>&1
prompt=$(cat "$tmp/prompt.args" 2>/dev/null || true)
expect_none "stop_hook_active does not alert"

# send <id> <to> ; ok <id> ; denied <id>
send() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"%s","name":"SendMessage","input":{"to":"%s","message":"x"}}]}}\n' "$1" "$2"; }
ok() { printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"%s","content":"sent"}]},"toolUseResult":{"success":true,"message":"sent"}}\n' "$1"; }
denied() { printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"%s","content":"Permission for this action has been denied.","is_error":true}]},"toolUseResult":"Error: Permission for this action has been denied."}\n' "$1"; }
peer() { printf '{"type":"user","isMeta":true,"origin":{"kind":"peer","name":"skills-b6"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
notification() { printf '{"type":"user","origin":{"kind":"task-notification"},"message":{"role":"user","content":"%s"}}\n' "$1"; }

reset_log
t="$tmp/reported.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; assistant_text "PR up sent"; } > "$t"
run "reported" "$t"
expect_none "a successful SendMessage to the controller counts as reported"

reset_log
t="$tmp/question.jsonl"
{ human "$brief"; send q1 "skills-b6"; ok q1; assistant_text "waiting on the ruling"; } > "$t"
run "question" "$t"
expect_none "a question sent by SendMessage, then a stop to wait, counts as reported"

reset_log
t="$tmp/denied.jsonl"
{ human "$brief"; send d1 "skills-b6"; denied d1; assistant_text "report denied"; } > "$t"
run "denied" "$t"
expect_alert "a denied SendMessage counts as not reported (#466)"

reset_log
t="$tmp/unsuccessful.jsonl"
{ human "$brief"; send f1 "skills-b6";
  printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"f1","content":"not sent"}]},"toolUseResult":{"success":false,"message":"not sent"}}\n'; } > "$t"
run "success false" "$t"
expect_alert "a SendMessage result with success:false counts as not reported"

reset_log
t="$tmp/other-recipient.jsonl"
{ human "$brief"; send o1 "someone-else"; ok o1; } > "$t"
run "other recipient" "$t"
expect_alert "a SendMessage to someone other than the controller is not a report"

reset_log
t="$tmp/ref.jsonl"
{ human "$brief"; send r1 "skills-b6 [3fa9c1]"; ok r1; } > "$t"
run "name with ref" "$t"
expect_none "a SendMessage to 'controller [ref]' counts as reported"

reset_log
printf '{"pid":%s,"sessionId":"ctl-session","name":"skills-b6","messagingSocketPath":"/run/ctl.sock"}\n' "$$" > "$home/.claude/sessions/$$.json"
t="$tmp/uds.jsonl"
{ human "$brief"; peer "ruling"; send u1 "uds:/run/ctl.sock"; ok u1; } > "$t"
run "uds reply" "$t"
expect_none "a reply to the controller's uds: address counts as reported"

reset_log
t="$tmp/stale-report.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "Codex findings, fix and send PR up again"; assistant_text "fixed"; } > "$t"
run "report before the controller's next message" "$t"
expect_alert "a report from an earlier turn does not cover a later peer-started turn"

reset_log
t="$tmp/notification.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; notification "background task done"; assistant_text "noted"; } > "$t"
run "task notification after report" "$t"
expect_none "a task notification does not start a turn that needs a report"

reset_log
t="$tmp/not-worker.jsonl"
{ human '<command-name>/implement</command-name>\n<command-args>820</command-args>'; assistant_text "dispatched"; } > "$t"
run "dispatcher" "$t"
expect_none "a session whose brief has no --controller is not a worker"

reset_log
t="$tmp/spec.jsonl"
{ human '<command-name>/implement-spec</command-name>\n<command-args>776 --slots 2 --controller \"skills-b6\"</command-args>'; assistant_text "stopped"; } > "$t"
run "spec run" "$t"
if printf '%s' "$prompt" | grep -q 'worker #776 stopped without reporting'; then
  echo "PASS: an /implement-spec brief with --controller is a worker"
else
  echo "FAIL: /implement-spec brief did not alert"; echo "  prompt: $prompt"; fails=1
fi

# Failure paths log and exit 0.
reset_log
t="$tmp/no-report.jsonl"
HERDR_PROMPT_RC=1 run "prompt rejected" "$t"
if grep -q 'not-sent' "$log" 2>/dev/null; then
  echo "PASS: a rejected herdr prompt is logged as not-sent, exit 0"
else
  echo "FAIL: a rejected prompt left no not-sent log line"; fails=1
fi

reset_log
printf '{"result":{"agents":[]}}\n' > "$tmp/agent-list.json"
run "no controller pane" "$t"
if [ -z "$prompt" ] && grep -q 'not-sent.*no herdr pane' "$log" 2>/dev/null; then
  echo "PASS: a missing controller pane is logged as not-sent, no prompt, exit 0"
else
  echo "FAIL: missing controller pane not logged"; echo "  prompt: $prompt"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
