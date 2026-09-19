#!/usr/bin/env bash
# Stop hook: tell the controller when a worker stops without reporting (#820).
#
# Contract: read the Stop event JSON on stdin. The session is a worker when its
# transcript opens with an `/implement` or `/implement-spec` brief carrying
# `--controller "<name>"`. A turn starts at a human prompt or a peer message
# that is not a subagent hand-back. The worker has reported when, after that
# turn start, a SendMessage to the controller came back with `success: true`.
# A stop while a subagent launched this turn has not handed back is a wait,
# not a finish. A launch is "handed back" in one of three shapes: an
# `.origin.senderTaskId` peer message (an anonymous `Agent` call's
# hand-back), a `<task-id>...</task-id>` tag (a task-notification), or a
# named teammate's plain-text `<teammate-message teammate_id="...">` reply
# (#859) — that last shape carries no `origin` at all, and its launch id is
# qualified (`name@session-...`) where the reply's `teammate_id` is bare, so
# matching strips the `@session-...` suffix before comparing. Otherwise
# submit one line into the controller's herdr pane
# with `herdr agent prompt` — a hook command, so the auto-mode classifier never
# sees it (#466's report was denied there). One alert per stop: every attempt
# is logged to ~/.claude/worker-stop-alerts.log keyed by session and the
# transcript's last entry, and a logged stop never alerts again. Always exit
# 0 — a hook failure must never block the worker's own stop.

set -u

log="$HOME/.claude/worker-stop-alerts.log"
event="$(cat)"

jq -e '.stop_hook_active != true' >/dev/null 2>&1 <<<"$event" || exit 0
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
session="$(jq -r '.session_id // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

# Transcript entries, skipping any line that does not parse (a line the
# harness is still writing).
entries() { jq -nc '[inputs | fromjson? | objects]' -R "$transcript" 2>/dev/null; }

# The brief: ticket number and controller name, or nothing for a non-worker.
IFS=$'\t' read -r n controller < <(entries | jq -r '
  [.[] | select(.type == "user" and .origin.kind == "human")
       | .message.content | strings
       | capture("<command-name>/implement(-spec)?</command-name>\\s*<command-args>(?<n>[0-9]+)\\b[^<]*--controller \"(?<c>[^\"]+)\"")]
  | first // empty | "\(.n)\t\(.c)"')
[ -n "${controller:-}" ] || exit 0

# The controller's live registry entry: its session id and messaging socket.
# Live means the pid's /proc starttime (field 22, after the `(comm)` field)
# equals the record's procStart — a stale record whose pid was reused has
# another, as in flow/lane's sessions reader.
ctl_session="" ctl_socket=""
for f in "$HOME"/.claude/sessions/*.json; do
  [ -e "$f" ] || continue
  IFS=$'\t' read -r pid start sid sock < <(jq -r --arg c "$controller" \
    'select(.name == $c) | "\(.pid)\t\(.procStart // "")\t\(.sessionId // "")\t\(.messagingSocketPath // "")"' "$f" 2>/dev/null)
  [[ "${pid:-}" =~ ^[0-9]+$ ]] || continue
  stat="$(cat "/proc/$pid/stat" 2>/dev/null)" || continue
  read -ra fields <<<"${stat##*) }"
  [ -n "$start" ] && [ "${fields[19]:-}" = "$start" ] || continue
  ctl_session="$sid" ctl_socket="$sock"
  break
done

# The verdict for this stop: `reported`, `waiting` on a subagent, or `silent`,
# plus the transcript's last entry as the stop's key.
IFS=$'\t' read -r verdict stop < <(entries | jq -r --arg c "$controller" --arg sock "$ctl_socket" '
  (to_entries | map(select(.value.type == "user"
      and (.value.origin.kind == "human" or (.value.origin.kind == "peer" and .value.origin.handback != true))))
   | last | .key // 0) as $start
  | .[($start + 1):] as $after
  | [$after[] | select(.type == "assistant") | .message.content[]?
      | select(.type == "tool_use" and .name == "SendMessage")
      | select(.input.to | strings | . == $c or startswith($c + " [") or ($sock != "" and . == "uds:" + $sock))
      | .id] as $sends
  | [$after[] | select(.type == "user" and (.toolUseResult | type) == "object" and .toolUseResult.success == true)
      | .message.content[]? | select(.type == "tool_result") | .tool_use_id | select(IN($sends[]))] as $delivered
  | [$after[] | .toolUseResult? | objects
      | select(.status == "async_launched" or .status == "teammate_spawned")
      | (.agentId // .agent_id) | select(strings)] as $launched
  | [$after[] | select(.type == "user") | (.origin.senderTaskId // empty),
      (.message.content | strings | scan("<task-id>([^<]+)</task-id>")[0]),
      (.message.content | strings | scan("<teammate-message teammate_id=\"([^\"]+)\"")[0])] as $returned
  # Background shells: the launch result carries `backgroundTaskId`, and only
  # a `<task-id>` notification that also carries a `<status>` ends one (#886).
  | [$after[] | .toolUseResult? | objects | .backgroundTaskId | select(strings)] as $tasks
  | [$after[] | select(.type == "user") | .message.content | strings
      | select(test("<status>")) | scan("<task-id>([^<]+)</task-id>")[0]] as $finished
  | ($tasks - $finished) as $unfinished
  # A teammate launch id is qualified (name@session-...); its reply id is
  # bare. Neither form appearing in $returned (both survive the set
  # difference, so the length is 2) means this launch is still unresolved.
  | [$launched[] | select(([., sub("@session-[^@]*$"; "")] - $returned | length) == 2)] as $unresolved
  | (if ($delivered | length) > 0 then "reported"
     elif (($unresolved | length) + ($unfinished | length)) > 0 then "waiting"
     else "silent" end) as $verdict
  | "\($verdict)\t\(last.uuid // "line \(length)")"')
[ "${verdict:-}" = "silent" ] || exit 0

# One alert per stop: a stop already in the log never alerts again.
key="$session"$'\t'"$stop"
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0

logline() { mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$1" "$2" >> "$log"; }

# Every herdr call below ends by a 12 s deadline, so the log line is written
# inside the hook's 15 s timeout.
deadline=$((SECONDS + 12))

worker_agent="$(timeout 2 herdr agent get "${HERDR_PANE_ID:-}" 2>/dev/null | jq -r '.result.agent.name // empty' 2>/dev/null)"
worker_agent="${worker_agent:-${HERDR_PANE_ID:-unknown pane}}"
alert="[worker-stop-alert] worker #$n stopped without reporting to $controller (herdr agent $worker_agent)"

pane=""
[ -n "$ctl_session" ] && pane="$(timeout 2 herdr agent list 2>/dev/null | jq -r --arg s "$ctl_session" \
  '.result.agents[]? | select(.agent_session.value == $s) | .pane_id' 2>/dev/null | head -n1)"
if [ -z "$pane" ]; then
  logline "not-sent" "no herdr pane for controller $controller: $alert"
  exit 0
fi

# herdr refuses a prompt to a blocked agent (`agent_blocked`) before sending
# any input, so retry that refusal with backoff while the deadline allows.
attempts=0 backoff=1
while :; do
  attempts=$((attempts + 1))
  if out="$(timeout 3 herdr agent prompt "$pane" "$alert" 2>&1)"; then
    logline "sent" "$pane: $alert"
    exit 0
  fi
  blocked="$(jq -r 'select(.error.code == "agent_blocked") | "yes"' <<<"$out" 2>/dev/null)"
  [ "$blocked" = yes ] && [ $((SECONDS + backoff + 3)) -le "$deadline" ] || break
  sleep "$backoff"
  backoff=$((backoff * 2))
done
if [ "$blocked" = yes ]; then
  logline "not-sent" "controller blocked: herdr agent prompt $pane refused agent_blocked on all $attempts attempts: $alert"
else
  logline "not-sent" "herdr agent prompt $pane failed: $(tr '\n' ' ' <<<"$out")"
fi
exit 0
