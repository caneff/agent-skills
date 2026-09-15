#!/usr/bin/env bash
# Stop hook: tell the controller when a worker stops without reporting (#820).
#
# Contract: read the Stop event JSON on stdin. The session is a worker when its
# transcript opens with an `/implement` or `/implement-spec` brief carrying
# `--controller "<name>"`. The worker has reported when, after its last human-
# or peer-origin prompt, a SendMessage to the controller came back with
# `success: true`. If it has not, submit one line into the controller's herdr
# pane with `herdr agent prompt` — a hook command, so the auto-mode classifier
# never sees it (#466's report was denied there). One alert per turn: every
# attempt is logged to ~/.claude/worker-stop-alerts.log keyed by session and
# turn, and a logged turn never alerts again. Always exit 0 — a hook failure
# must never block the worker's own stop.

set -u

log="$HOME/.claude/worker-stop-alerts.log"
event="$(cat)"

jq -e '.stop_hook_active != true' >/dev/null 2>&1 <<<"$event" || exit 0
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
session="$(jq -r '.session_id // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

# The brief: ticket number and controller name, or nothing for a non-worker.
brief="$(jq -rs '
  [.[] | select(.type == "user" and .origin.kind == "human")
       | .message.content | strings
       | capture("<command-name>/implement(-spec)?</command-name>\\s*<command-args>(?<n>[0-9]+)\\b[^<]*--controller \"(?<c>[^\"]+)\"")]
  | first // empty | "\(.n)\t\(.c)"' "$transcript" 2>/dev/null)"
[ -n "$brief" ] || exit 0
n="${brief%%$'\t'*}"
controller="${brief#*$'\t'}"

# The controller's live registry entry: its session id and messaging socket.
ctl_session="" ctl_socket=""
for f in "$HOME"/.claude/sessions/*.json; do
  [ -e "$f" ] || continue
  entry="$(jq -r --arg c "$controller" 'select(.name == $c) | "\(.pid)\t\(.sessionId // "")\t\(.messagingSocketPath // "")"' "$f" 2>/dev/null)"
  [ -n "$entry" ] || continue
  pid="${entry%%$'\t'*}"
  kill -0 "$pid" 2>/dev/null || continue
  rest="${entry#*$'\t'}"
  ctl_session="${rest%%$'\t'*}"
  ctl_socket="${rest#*$'\t'}"
  break
done

# Reported? A successful SendMessage to the controller — by name, by
# `name [ref]`, or by its `uds:` socket address — after the last turn start.
turn_and_reported="$(jq -rs --arg c "$controller" --arg sock "uds:$ctl_socket" '
  (to_entries | map(select(.value.type == "user" and (.value.origin.kind == "human" or .value.origin.kind == "peer"))) | last) as $turn
  | .[($turn.key + 1):] as $after
  | [$after[] | select(.type == "assistant") | .message.content[]?
      | select(.type == "tool_use" and .name == "SendMessage")
      | select(.input.to == $c or (.input.to | startswith($c + " [")) or ($sock != "uds:" and .input.to == $sock))
      | .id] as $ids
  | [$after[] | select(.type == "user" and (.toolUseResult | type) == "object" and .toolUseResult.success == true)
      | .message.content[]? | select(.type == "tool_result") | .tool_use_id | select(. as $i | $ids | index($i))]
  | "\($turn.value.uuid // $turn.key)\t\(if length > 0 then "yes" else "no" end)"' "$transcript" 2>/dev/null)"
[ -n "$turn_and_reported" ] || exit 0
turn="${turn_and_reported%%$'\t'*}"
[ "${turn_and_reported#*$'\t'}" = "no" ] || exit 0

# One alert per turn: a turn already in the log never alerts again.
key="$session"$'\t'"$turn"
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0

logline() { mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$1" "$2" >> "$log"; }

worker_agent="$(herdr agent get "${HERDR_PANE_ID:-}" 2>/dev/null | jq -r '.result.agent.name // empty' 2>/dev/null)"
worker_agent="${worker_agent:-${HERDR_PANE_ID:-unknown pane}}"
alert="[worker-stop-alert] worker #$n stopped without reporting to $controller (herdr agent $worker_agent)"

pane=""
[ -n "$ctl_session" ] && pane="$(herdr agent list 2>/dev/null | jq -r --arg s "$ctl_session" \
  '.result.agents[]? | select(.agent_session.value == $s) | .pane_id' 2>/dev/null | head -n1)"
if [ -z "$pane" ]; then
  logline "not-sent" "no herdr pane for controller $controller: $alert"
  exit 0
fi

if out="$(herdr agent prompt "$pane" "$alert" 2>&1)"; then
  logline "sent" "$pane: $alert"
else
  logline "not-sent" "herdr agent prompt $pane failed: $(tr '\n' ' ' <<<"$out")"
fi
exit 0
