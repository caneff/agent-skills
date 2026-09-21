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
# `agent get` names the worker's agent, `agent prompt` records its target and
# its alert text in separate files.
stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") cat "$tmp/agent-list.json" ;;
  "agent get") printf '{"result":{"agent":{"name":"skills-820","pane_id":"%s"}}}\n' "\$3" ;;
  "agent prompt")
    [ -n "\${HERDR_PROMPT_HANG:-}" ] && exec sleep 30
    # HERDR_PROMPT_BLOCKED=<k>: the first k prompts are refused as blocked.
    tries=\$(( \$(cat "$tmp/prompt.tries" 2>/dev/null || echo 0) + 1 )); echo "\$tries" > "$tmp/prompt.tries"
    if [ "\$tries" -le "\${HERDR_PROMPT_BLOCKED:-0}" ]; then
      echo '{"error":{"code":"agent_blocked","message":"agent is blocked"},"id":"cli:agent:prompt"}'; exit 1
    fi
    printf '%s' "\$3" > "$tmp/prompt.pane"; printf '%s' "\$4" > "$tmp/prompt.text"
    exit "\${HERDR_PROMPT_RC:-0}" ;;
esac
STUB
chmod +x "$stubdir/herdr"

home="$tmp/home"
mkdir -p "$home/.claude/sessions"
# The controller session is this test's own shell: a live pid whose
# procStart is its /proc starttime (field 22).
stat=$(cat /proc/$$/stat); ctl_start=$(set -- ${stat##*) }; echo "${20}")
printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-b6"}\n' "$$" "$ctl_start" > "$home/.claude/sessions/$$.json"
agents_ok='{"result":{"agents":[{"pane_id":"w9:p1","agent_session":{"value":"ctl-session"}},{"pane_id":"w0:p1","agent_session":{"value":"dead-session"}}]}}'
printf '%s\n' "$agents_ok" > "$tmp/agent-list.json"
log="$home/.claude/worker-stop-alerts.log"

brief='<command-message>implement</command-message>\n<command-name>/implement</command-name>\n<command-args>820 --tier heavy --controller \"skills-b6\"</command-args>'

# Transcript lines.
human() { printf '{"type":"user","origin":{"kind":"human"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
assistant_text() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"%s"}]}}\n' "$1"; }
# send <id> <to> ; ok <id> ; denied <id>
send() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"%s","name":"SendMessage","input":{"to":"%s","message":"x"}}]}}\n' "$1" "$2"; }
ok() { printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"%s","content":"sent"}]},"toolUseResult":{"success":true,"message":"sent"}}\n' "$1"; }
denied() { printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"%s","content":"Permission for this action has been denied.","is_error":true}]},"toolUseResult":"Error: Permission for this action has been denied."}\n' "$1"; }
peer() { printf '{"type":"user","isMeta":true,"origin":{"kind":"peer","name":"skills-b6"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
notification() { printf '{"type":"user","origin":{"kind":"task-notification"},"message":{"role":"user","content":"%s"}}\n' "$1"; }
# launch <agentId> ; teammate_launch <agentId> [name] ; handback <agentId>
launch() { printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t-%s","content":"Async agent launched"}]},"toolUseResult":{"isAsync":true,"status":"async_launched","agentId":"%s"}}\n' "$1" "$1"; }
# The Agent-tool-as-teammate shape (#856): status teammate_spawned, id under
# agent_id (snake_case), no agentId field at all. <name> defaults to <agentId>
# for a bare (unqualified) id; pass it explicitly for a qualified one
# (`name@session-...`, #859) since the bare name is what a real report's
# teammate_id carries.
teammate_launch() { local id=$1 name=${2:-$1}; printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t-%s","content":"Spawned successfully."}]},"toolUseResult":{"status":"teammate_spawned","agent_id":"%s","name":"%s"}}\n' "$id" "$id" "$name"; }
handback() { printf '{"type":"user","origin":{"kind":"peer","from":"%s","senderTaskId":"%s","handback":true},"message":{"role":"user","content":"[Subagent hand-back] report"}}\n' "$1" "$1"; }
# teammate_report <bare-id> : a named teammate's actual return shape (#859) —
# a plain-text message with no `origin` field at all, carrying a
# `<teammate-message teammate_id="...">` wrapper around an idle_notification.
teammate_report() { printf '{"type":"user","message":{"role":"user","content":"Another Claude session sent a message:\\n<teammate-message teammate_id=\\"%s\\" color=\\"blue\\">\\n{\\"type\\":\\"idle_notification\\",\\"from\\":\\"%s\\",\\"idleReason\\":\\"available\\",\\"result\\":\\"ok\\"}\\n</teammate-message>"}}\n' "$1" "$1"; }
# bg_launch <task-id> : a Bash with run_in_background:true — an assistant
# tool_use plus the result whose toolUseResult carries `backgroundTaskId`
# (#886). It is resolved by a `<task-id>` notification carrying a `<status>`.
bg_launch() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-%s","name":"Bash","input":{"command":"just check-full","run_in_background":true}}]}}\n' "$1"
  printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu-%s","content":"Command running in background with ID: %s"}]},"toolUseResult":{"stdout":"","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false,"backgroundTaskId":"%s"}}\n' "$1" "$1" "$1"; }
# monitor_launch <task-id> : the Monitor tool's launch result (#886).
monitor_launch() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"tu-%s","name":"Monitor","input":{"command":"tail -F progress","description":"job progress"}}]}}\n' "$1"
  printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu-%s","content":"Monitor started (task %s)"}]},"toolUseResult":{"taskId":"%s","timeoutMs":1800000,"persistent":false}}\n' "$1" "$1" "$1"; }
# task_done <task-id> [status] : the terminal notification for a background
# shell or a monitor — a `<task-id>` with a `<status>`.
task_done() { printf '{"type":"user","origin":{"kind":"task-notification"},"message":{"role":"user","content":"<task-notification>\\n<task-id>%s</task-id>\\n<status>%s</status>\\n<summary>done</summary>\\n</task-notification>"}}\n' "$1" "${2:-completed}"; }
# monitor_event <task-id> : a Monitor event notification — a `<task-id>` with
# no `<status>`. The monitor is still running, so this is not a return.
monitor_event() { printf '{"type":"user","origin":{"kind":"task-notification"},"message":{"role":"user","content":"<task-notification>\\n<task-id>%s</task-id>\\n<summary>Monitor event: job progress</summary>\\n<event>13:45:43 tick</event>\\n</task-notification>"}}\n' "$1"; }
# task_stop <task-id> : the worker stopping a monitor itself.
task_stop() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"ts-%s","name":"TaskStop","input":{"task_id":"%s"}}]}}\n' "$1" "$1"; }
# work : a tool call that is not a report — the mark of a turn that did
# something and therefore owes the controller a report (#886).
work() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"e-1","name":"Edit","input":{"file_path":"a.js"}}]}}\n'
  printf '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"e-1","content":"ok"}]},"toolUseResult":{"filePath":"a.js"}}\n'; }

# task_poll <id> : a TaskOutput poll of a background task or subagent (#900).
task_poll() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"po-%s","name":"TaskOutput","input":{"task_id":"%s"}}]}}\n' "$1" "$1"; }
# bash_cmd <text> : a Bash call whose command merely mentions text.
bash_cmd() { printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"bc-1","name":"Bash","input":{"command":"%s"}}]}}\n' "$1"; }

fails=0
# run <name> <transcript-file> [stop_hook_active] -> sets $pane and $text
# (the recorded prompt's target and alert, empty if no prompt was sent)
run() {
  local name=$1 transcript=$2 active=${3:-false} out rc
  rm -f "$tmp/prompt.pane" "$tmp/prompt.text"
  out=$(jq -n --arg t "$transcript" --argjson a "$active" '{hook_event_name:"Stop",session_id:"w",transcript_path:$t,stop_hook_active:$a}' \
        | HOME="$home" HERDR_PANE_ID="w2W:p1" PATH="$stubdir:$PATH" bash "$hook" 2>&1)
  rc=$?
  pane=$(cat "$tmp/prompt.pane" 2>/dev/null || true)
  text=$(cat "$tmp/prompt.text" 2>/dev/null || true)
  if [ "$rc" != 0 ]; then
    echo "FAIL: $name — want exit 0, got $rc"; echo "  out: $out"; fails=1
  fi
}
# expect_alert <name> [ticket]
expect_alert() {
  local name=$1 n=${2:-820}
  if [ "$pane" = "w9:p1" ] && printf '%s' "$text" | grep -q "worker #$n stopped without reporting" \
     && printf '%s' "$text" | grep -q 'skills-820'; then
    echo "PASS: $name"
  else
    echo "FAIL: $name — want an alert for #$n to w9:p1"; echo "  pane: $pane text: $text"; fails=1
  fi
}
expect_none() {
  local name=$1
  if [ -z "$pane" ]; then echo "PASS: $name"; else echo "FAIL: $name — want no prompt"; echo "  pane: $pane text: $text"; fails=1; fi
}
reset_log() { rm -f "$log"; }

# A worker whose turn ended with no report alerts the controller.
reset_log
t="$tmp/no-report.jsonl"
{ human "$brief"; assistant_text "done, report in my pane"; } > "$t"
run "no report" "$t"
expect_alert "worker that never reported alerts the controller's pane"
# Read the recorded file itself: `$(...)` would strip a trailing newline.
if [ "$(wc -l < "$tmp/prompt.text")" = 0 ] && ! grep -q '^! ' "$tmp/prompt.text"; then
  echo "PASS: alert is one line with no \`! \` command"
else
  echo "FAIL: alert text is not one plain line: $text"; fails=1
fi

# The same stop, evaluated again, does not re-fire; a later stop does.
run "same stop again" "$t"
expect_none "a re-evaluated stop that already alerted does not re-fire"
assistant_text "woke on a notification, still no report" >> "$t"
run "a later stop" "$t"
expect_alert "a later stop, still without a report, alerts again"

# stop_hook_active: the harness is re-running Stop hooks for this stop.
reset_log
run "stop_hook_active" "$t" true
expect_none "stop_hook_active does not alert"

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
printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-b6","messagingSocketPath":"/run/ctl.sock"}\n' "$$" "$ctl_start" > "$home/.claude/sessions/$$.json"
t="$tmp/uds.jsonl"
{ human "$brief"; peer "ruling"; send u1 "uds:/run/ctl.sock"; ok u1; } > "$t"
run "uds reply" "$t"
expect_none "a reply to the controller's uds: address counts as reported"

reset_log
t="$tmp/stale-report.jsonl"
# The worker did the fix work the message asked for and then stopped: work
# since the last report is what makes the report stale (#886).
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "Codex findings, fix and send PR up again"; work; assistant_text "fixed"; } > "$t"
run "report before the controller's next message" "$t"
expect_alert "a report from an earlier turn does not cover a later peer-started turn"

reset_log
t="$tmp/notification.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; notification "background task done"; assistant_text "noted"; } > "$t"
run "task notification after report" "$t"
expect_none "a task notification does not start a turn that needs a report"

# Subagents: a stop while one is out is a wait; a hand-back is not a new turn.
reset_log
t="$tmp/waiting.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings"; launch a1; launch a2; assistant_text "reviewers running"; } > "$t"
run "reviewers out" "$t"
expect_none "a stop while this turn's subagents are out does not alert"
{ handback a1; assistant_text "one of two back"; } >> "$t"
run "one reviewer back" "$t"
expect_none "a hand-back that leaves another subagent out does not alert"
{ notification '<task-notification><task-id>a2</task-id><status>failed</status></task-notification>'; assistant_text "all back, stopping"; } >> "$t"
run "all reviewers back" "$t"
expect_alert "once every subagent is back, a stop without a report alerts"

# A subagent launched as a teammate (Agent tool, status teammate_spawned,
# id under agent_id) is still out: a stop while it's out is a wait, not a
# silent stop (#856 — worker #854 was falsely flagged silent on this shape).
reset_log
t="$tmp/teammate-waiting.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings"; teammate_launch tally-854; assistant_text "reviewer running"; } > "$t"
run "teammate reviewer out" "$t"
expect_none "a stop while a teammate-spawned subagent is out does not alert"
{ handback tally-854; assistant_text "back, stopping"; } >> "$t"
run "teammate reviewer back" "$t"
expect_alert "once the teammate-spawned subagent is back, a stop without a report alerts"

# The real teammate-return shape (#859): the launched id is qualified
# (`tally-859@session-2b7ae693`), the report is a plain-text
# `<teammate-message teammate_id="tally-859">` with no `origin` field at
# all — not a hand-back. Once it lands, `$launched - $returned` must empty;
# otherwise this entry is stuck `waiting` forever and a later silent stop
# never alerts (#820's failure mode again, hidden behind a benign verdict).
reset_log
t="$tmp/teammate-report.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings";
  teammate_launch tally-859@session-2b7ae693 tally-859;
  assistant_text "reviewer running"; } > "$t"
run "qualified teammate out" "$t"
expect_none "a stop while a qualified-id teammate is out does not alert"
{ teammate_report tally-859; assistant_text "reviewer reported back, stopping"; } >> "$t"
run "qualified teammate reported" "$t"
expect_alert "once the qualified-id teammate's report lands, a stop without a further report alerts"

reset_log
t="$tmp/handback-report.jsonl"
{ human "$brief"; launch a1; handback a1; send s1 "skills-b6"; ok s1; assistant_text "PR up"; } > "$t"
run "report after hand-back" "$t"
expect_none "a report sent after a hand-back covers the turn the hand-back did not restart"

# A background shell is out: the worker launched `just check-full` and went
# idle waiting for it (#886, false alert 1 of 3).
reset_log
t="$tmp/bg-shell.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings"; work;
  bg_launch b06vc2csw; assistant_text "check-full running"; } > "$t"
run "background shell out" "$t"
expect_none "a stop while a background shell is out does not alert"
{ task_done b06vc2csw completed; assistant_text "check green, stopping"; } >> "$t"
run "background shell done" "$t"
expect_alert "once the background shell completes, a stop without a report alerts"

# A Monitor task is out (#886, false alert 2 of 3). Its event notifications
# carry a `<task-id>` and no `<status>`: the monitor is still running, so an
# event is not its return.
reset_log
t="$tmp/monitor.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings"; work;
  monitor_launch boirnz0ok; assistant_text "watching the job"; } > "$t"
run "monitor out" "$t"
expect_none "a stop while a Monitor task is out does not alert"
{ monitor_event boirnz0ok; assistant_text "tick noted, still waiting"; } >> "$t"
run "monitor event" "$t"
expect_none "a Monitor event does not end the monitor, so the stop still does not alert"
{ task_done boirnz0ok completed; assistant_text "job done, stopping"; } >> "$t"
run "monitor ended" "$t"
expect_alert "once the monitor ends, a stop without a report alerts"

# A monitor the worker stopped itself is no longer outstanding — otherwise
# the entry sits `waiting` forever and no later silent stop ever alerts.
reset_log
t="$tmp/monitor-stopped.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "fix the findings"; work;
  monitor_launch bq1w2e3r4; task_stop bq1w2e3r4; assistant_text "stopped watching"; } > "$t"
run "monitor stopped by the worker" "$t"
expect_alert "a monitor the worker stopped with TaskStop is not still outstanding"

# Already reported, then answered a message that needed no reply (#886,
# false alert 3 of 3 — the one a diligent controller manufactures for
# itself by closing its own loops). Nothing was done since the report, so
# the report still stands.
reset_log
t="$tmp/loop-closed.jsonl"
{ human "$brief"; send s1 "skills-b6"; ok s1; peer "merged, sha 1a2b3c — nothing needed"; assistant_text "noted"; } > "$t"
run "message needing no reply" "$t"
expect_none "a message needing no reply, answered with no work, does not alert"

# A report sent inside this turn stands even though the worker kept working
# after it — the other half of the reported verdict, which the loop-closed
# rule below does not cover because work followed the report.
reset_log
t="$tmp/reported-then-worked.jsonl"
{ human "$brief"; peer "what does the failing check say?"; work; send s1 "skills-b6"; ok s1;
  work; assistant_text "answered, then kept going"; } > "$t"
run "reported this turn, then kept working" "$t"
expect_none "a report inside this turn covers the stop even when work followed it"

# An id with no liveness evidence since the turn start is not out, and that bound is load-bearing: 45% of
# real background tasks never emit a terminal notification, so a set carried
# across turns would let one stale id hold the verdict at `waiting` for the
# rest of the session and the alert would never fire again (#900, and
# docs/research/2026-09-19-background-task-terminal-states.md). The price is
# the case below: a job that never finished does not cover a later stop
# unless something since the turn start names it (the tests further down).
reset_log
t="$tmp/bg-across-turns.jsonl"
{ human "$brief"; bg_launch bnever1; assistant_text "check-full running"; } > "$t"
run "background shell out" "$t"
expect_none "a stop while a background shell is out does not alert"
{ peer "new task: fix the flaky test"; work; assistant_text "fixed it"; } >> "$t"
run "stale never-finished job" "$t"
expect_alert "a never-terminated job does not suppress a later genuine silent stop"

# Liveness evidence (#900): a launch from an earlier turn stays out across an
# inbound message only while something since the turn start names its id.
reset_log
t="$tmp/bg-polled.jsonl"
{ human "$brief"; bg_launch bpoll1; assistant_text "check-full running"; peer "status?"; task_poll bpoll1; assistant_text "still running"; } > "$t"
run "background shell polled" "$t"
expect_none "a background shell launched last turn and polled since the turn start is still out"

reset_log
t="$tmp/monitor-evented.jsonl"
{ human "$brief"; monitor_launch bmon1; assistant_text "watching"; peer "status?"; monitor_event bmon1; assistant_text "tick"; } > "$t"
run "monitor event this turn" "$t"
expect_none "a monitor launched last turn with an event since the turn start is still out"

reset_log
t="$tmp/reviewer-across-message.jsonl"
{ human "$brief"; launch r1; assistant_text "reviewer running"; peer "status?"; task_poll r1; assistant_text "still out"; } > "$t"
run "reviewer polled across a message" "$t"
expect_none "a subagent launched last turn and polled since the turn start is still out"

reset_log
t="$tmp/reviewer-untouched.jsonl"
{ human "$brief"; launch r2; assistant_text "reviewer running"; peer "status?"; assistant_text "noted"; } > "$t"
run "reviewer with no evidence" "$t"
expect_alert "a subagent launched last turn and untouched since the turn start does not suppress a silent stop"

reset_log
t="$tmp/polled-then-done.jsonl"
{ human "$brief"; bg_launch bpoll2; peer "status?"; task_done bpoll2 completed; task_poll bpoll2; assistant_text "done"; } > "$t"
run "polled after it finished" "$t"
expect_alert "a polled task that already reached a terminal state is not out"

reset_log
t="$tmp/mention-only.jsonl"
{ human "$brief"; launch a0037b86e988b4825; assistant_text "reviewer running"; peer "status?";
  bash_cmd "grep -c a0037b86e988b4825 .scratch/agents.log"; assistant_text "noted"; } > "$t"
run "id mentioned in a command" "$t"
expect_alert "an id that only appears in a command is not evidence of life"

reset_log
t="$tmp/peer-mention.jsonl"
{ human "$brief"; launch a0037b86e988b4826; assistant_text "reviewer running"; peer "is a0037b86e988b4826 still out?"; assistant_text "noted"; } > "$t"
run "id named in a peer message" "$t"
expect_alert "an id a peer message names is not evidence of life"

reset_log
t="$tmp/id-prefix.jsonl"
{ human "$brief"; bg_launch b0kjm5mmm; bg_launch b0kjm5mmmX; assistant_text "two out"; peer "status?";
  task_done b0kjm5mmmX completed; task_poll b0kjm5mmmX; assistant_text "one done"; } > "$t"
run "id that prefixes another" "$t"
expect_alert "polling one id does not keep an id it is a prefix of out"

# The resolution sets are read over the whole transcript: an id that ended in
# an earlier turn stays ended when a later poll names it.
reset_log
t="$tmp/handed-back-earlier.jsonl"
{ human "$brief"; launch r3; handback r3; peer "status?"; task_poll r3; assistant_text "back already"; } > "$t"
run "subagent handed back last turn, polled this turn" "$t"
expect_alert "a subagent handed back in an earlier turn is not out because it was polled"

reset_log
t="$tmp/teammate-reported-earlier.jsonl"
{ human "$brief"; teammate_launch tally-900@session-2b7ae693 tally-900; teammate_report tally-900; peer "status?";
  task_poll tally-900; assistant_text "reported already"; } > "$t"
run "teammate reported last turn, polled this turn" "$t"
expect_alert "a teammate that reported in an earlier turn is not out because it was polled"

reset_log
t="$tmp/finished-earlier.jsonl"
{ human "$brief"; bg_launch bfin1; task_done bfin1 completed; peer "status?"; task_poll bfin1; assistant_text "finished already"; } > "$t"
run "task finished last turn, polled this turn" "$t"
expect_alert "a task that finished in an earlier turn is not out because it was polled"

reset_log
t="$tmp/torn.jsonl"
{ human "$brief"; send x1 "skills-b6"; denied x1;
  printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"n1","name":"SendMessage","input":{"to":null}}]}}\n';
  printf '{"type":"assistant","message":{"con'; } > "$t"
run "torn last line" "$t"
expect_alert "a half-written last line and a non-string recipient still alert"

reset_log
t="$tmp/not-worker.jsonl"
{ human '<command-name>/implement</command-name>\n<command-args>820</command-args>'; assistant_text "dispatched"; } > "$t"
run "dispatcher" "$t"
expect_none "a session whose brief has no --controller is not a worker"

reset_log
t="$tmp/spec.jsonl"
{ human '<command-name>/implement-spec</command-name>\n<command-args>776 --slots 2 --controller \"skills-b6\"</command-args>'; assistant_text "stopped"; } > "$t"
run "spec run" "$t"
expect_alert "an /implement-spec brief with --controller is a worker" 776

# A dead session file with the controller's name is ignored: its pid is gone.
reset_log
printf '{"pid":999999999,"sessionId":"dead-session","name":"skills-b6"}\n' > "$home/.claude/sessions/0.json"
t="$tmp/no-report.jsonl"
run "dead registry entry" "$t"
expect_alert "a dead registry entry with the controller's name is skipped"
rm -f "$home/.claude/sessions/0.json"

# A stale record whose pid was reused by a live process is skipped: its
# procStart does not match that pid's starttime.
reset_log
printf '{"pid":%s,"procStart":"1","sessionId":"dead-session","name":"skills-b6"}\n' "$$" > "$home/.claude/sessions/0.json"
run "reused pid" "$t"
expect_alert "a same-name record with a reused pid does not hide the real controller"
rm -f "$home/.claude/sessions/0.json"

# Failure paths log and exit 0.
reset_log
HERDR_PROMPT_RC=1 run "prompt rejected" "$t"
if grep -q 'not-sent' "$log" 2>/dev/null; then
  echo "PASS: a rejected herdr prompt is logged as not-sent, exit 0"
else
  echo "FAIL: a rejected prompt left no not-sent log line"; fails=1
fi

# A blocked controller: retry with backoff inside the hook's budget.
reset_log; rm -f "$tmp/prompt.tries"
HERDR_PROMPT_BLOCKED=2 run "blocked, then free" "$t"
expect_alert "a prompt refused as blocked is retried until the controller accepts it"
reset_log; rm -f "$tmp/prompt.tries"
start=$SECONDS
HERDR_PROMPT_BLOCKED=99 run "blocked throughout" "$t"
if [ -z "$pane" ] && [ "$(cat "$tmp/prompt.tries")" -ge 2 ] && [ $((SECONDS - start)) -lt 15 ] \
   && grep -q $'not-sent\tcontroller blocked:' "$log" 2>/dev/null; then
  echo "PASS: a controller blocked throughout is retried, then logged as not-sent: blocked, within 15 s"
else
  echo "FAIL: blocked controller — tries $(cat "$tmp/prompt.tries"), $((SECONDS - start)) s, log: $(cat "$log" 2>/dev/null)"; fails=1
fi
rm -f "$tmp/prompt.tries"

reset_log
HERDR_PROMPT_HANG=1 run "prompt hangs" "$t"
if grep -q 'not-sent' "$log" 2>/dev/null; then
  echo "PASS: a hung herdr prompt times out and is logged as not-sent"
else
  echo "FAIL: a hung prompt left no not-sent log line"; fails=1
fi

reset_log
printf '{"result":{"agents":[]}}\n' > "$tmp/agent-list.json"
run "no controller pane" "$t"
if [ -z "$pane" ] && grep -q 'not-sent.*no herdr pane' "$log" 2>/dev/null; then
  echo "PASS: a missing controller pane is logged as not-sent, no prompt, exit 0"
else
  echo "FAIL: missing controller pane not logged"; echo "  pane: $pane"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
