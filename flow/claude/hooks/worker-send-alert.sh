#!/usr/bin/env bash
# PostToolUse hook on SendMessage: tell the controller's pane at once when a
# worker's send to its controller failed (#1540). Two episodes in one week had
# a worker whose sends all failed (a Claude Code upgrade moved the socket
# directory) while nothing said so until the worker stopped;
# worker-stop-alert.sh fires at the stop, this fires at the failed send.
#
# Contract: read the PostToolUse event JSON on stdin (a live firing, 2026-10-16:
# the event carries `tool_name`, `tool_use_id`, `tool_input.to` and
# `tool_response`, whose `success` is false on a send that did not deliver;
# PostToolUseFailure did not fire for it). The session is a worker when its
# transcript opens with an `/implement` or `/implement-spec` brief carrying
# `--controller "<name>"`. The send is to the controller when `to` is the
# brief's literal, a resolved live session name or a resolved `uds:` address —
# the same match set as the stop hook, from the shared lib. A response whose
# `success` is not true is a failed send: one line goes into the controller's
# herdr pane with `herdr agent prompt`, a hook command the auto-mode
# classifier never sees. A controller named `drain` is no session, so no
# alert. One alert per send: every attempt is logged to
# ~/.claude/worker-send-alerts.log keyed by `tool_use_id`, and a logged send
# never alerts again. An event with no `tool_response` is logged, never read as
# delivered or as failed. Always exit 0 — a hook failure must never block the
# worker's own tool call.

set -u

hook_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
log="$HOME/.claude/worker-send-alerts.log"
lib_missing() { # <what's wrong> -> logs and exits 0, no lib functions required
  mkdir -p "$(dirname "$log")"
  printf '%s\t%s\tnot-sent\t%s\n' "$(date -u +%FT%TZ)" "lib-missing" "$1" >> "$log"
  exit 0
}
source "$hook_dir/worker-alert-lib.sh" 2>/dev/null || \
  lib_missing "missing $hook_dir/worker-alert-lib.sh — hook cannot resolve a controller"
for fn in worker_alert_read_brief worker_alert_resolve_session worker_alert_logline \
          worker_alert_worker_agent_name worker_alert_controller_pane \
          worker_alert_resolve_controller worker_alert_prompt_pane; do
  declare -F "$fn" >/dev/null || lib_missing "$hook_dir/worker-alert-lib.sh loaded but does not define $fn"
done

event="$(cat)"

[ "$(jq -r '.tool_name // ""' <<<"$event" 2>/dev/null)" = SendMessage ] || exit 0
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

IFS=$'\t' read -r n controller < <(worker_alert_read_brief "$transcript")
[ -n "${controller:-}" ] && [ "$controller" != drain ] || exit 0

to="$(jq -r '.tool_input.to // "" | strings' <<<"$event" 2>/dev/null)"
[ -n "$to" ] || exit 0
worker_alert_resolve_controller "$controller"
to_controller=""
for nm in "$controller" ${names[@]+"${names[@]}"} ${sockets[@]+"${sockets[@]}"}; do
  [ "$to" = "$nm" ] || [[ "$to" == "$nm ["* ]] && to_controller=yes
done
[ -n "$to_controller" ] || exit 0

tool_use_id="$(jq -r '.tool_use_id // ""' <<<"$event" 2>/dev/null)"
key="${tool_use_id:-$(jq -r '.session_id // ""' <<<"$event" 2>/dev/null)}"
logline() { worker_alert_logline "$log" "$key" "$1" "$2"; }

# The answer, three ways: delivered, failed, or absent. `success` must be
# exactly true to count as delivered; a bare error string is a failure too.
verdict="$(jq -r 'if (has("tool_response") | not) or .tool_response == null then "absent"
                  elif (.tool_response | type) == "object" and .tool_response.success == true then "delivered"
                  else "failed" end' <<<"$event" 2>/dev/null)"
case "$verdict" in
  delivered) exit 0 ;;
  failed) ;;
  *) grep -qF -- "$key"$'\t' "$log" 2>/dev/null || logline "not-sent" "no tool_response in the event for the send to $to; nothing alerted"; exit 0 ;;
esac

# One alert per send: a send already in the log never alerts again.
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0

reason="$(jq -r '.tool_response | if type == "object" then (.message // "") else tostring end | split("\n")[0]' <<<"$event" 2>/dev/null)"
deadline=$((SECONDS + 10))
worker_agent="$(worker_alert_worker_agent_name)"
alert="[worker-send-alert] worker #$n's SendMessage to $to failed: ${reason:-no reason given} (herdr agent $worker_agent)"

pane="$(worker_alert_controller_pane "$ctl_session")"
if [ -z "$pane" ]; then
  logline "not-sent" "no herdr pane for controller $controller: $alert"
  exit 0
fi
worker_alert_prompt_pane "$pane" "$alert" "$deadline"
logline "$prompt_status" "$prompt_msg"
exit 0
