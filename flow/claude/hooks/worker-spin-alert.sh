#!/usr/bin/env bash
# PostToolUse hook: tell the controller when a worker repeats one tool call
# without end (#925).
#
# Why here: the Stop hook only fires when a worker stops, and a worker
# spinning on `echo ok` never does. Time-in-state and transcript mtime read
# healthy too, because the spin itself writes the transcript. A PostToolUse
# hook runs inside the turn, after every call, so it is the one place the
# repetition is visible as it happens.
#
# Spin: the same tool with byte-identical input, N (default 20, SPIN_N) times
# in a row with no other tool call between. The observed loop ran 180; a retry
# or a sanctioned poll stays in single digits, and a `Monitor` until-loop is
# one call. Only the transcript tail is read, so the per-call cost stays flat and `count` is a floor: a longer run reports the window it saw.
#
# Modes:
#   --classify <transcript>   print {spinning, tool, input, count} and exit —
#                             what a controller runs against a transcript on demand.
#   (stdin: PostToolUse event) alert the controller's herdr pane once per run,
#                             logged to ~/.claude/worker-spin-alerts.log.
# Always exit 0 in hook mode — a hook failure must never block the worker.

set -u
N="${SPIN_N:-20}"

classify() { # <transcript> -> JSON
  tail -n $((N * 4 + 40)) "$1" 2>/dev/null | jq -nRc --argjson n "$N" '
    [inputs | fromjson? | objects | select(.type == "assistant" and .isSidechain != true)
      | .message.content[]? | select(.type == "tool_use") | {name, input}] | reverse as $calls
    | ($calls[0] // null) as $l
    | (reduce $calls[] as $c ({n: 0, stop: false};
        if .stop then .
        elif $c == $l then .n += 1
        else .stop = true end) | .n) as $count
    | {spinning: ($count >= $n), tool: ($l.name // null), input: ($l.input // null), count: $count}'
}

if [ "${1:-}" = "--classify" ]; then classify "${2:?transcript path}"; exit 0; fi

log="$HOME/.claude/worker-spin-alerts.log"
event="$(cat)"
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
session="$(jq -r '.session_id // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

verdict="$(classify "$transcript")"
jq -e '.spinning == true' >/dev/null 2>&1 <<<"$verdict" || exit 0

# A worker's brief names its ticket and controller; anything else is not one.
IFS=$'\t' read -r n controller < <(jq -nc '[inputs | fromjson? | objects] ' -R "$transcript" 2>/dev/null | jq -r '
  [.[] | select(.type == "user" and .origin.kind == "human") | .message.content | strings
       | capture("<command-name>/implement(-spec)?</command-name>\\s*<command-args>(?<n>[0-9]+)\\b[^<]*--controller \"(?<c>[^\"]+)\"")]
  | first // empty | "\(.n)\t\(.c)"')
[ -n "${controller:-}" ] || exit 0

tool="$(jq -r '.tool' <<<"$verdict")"
input="$(jq -c '.input' <<<"$verdict" | cut -c1-120)"
count="$(jq -r '.count' <<<"$verdict")"

# One alert per run of repeats: keyed by session, tool and input, so a run
# that keeps growing does not re-alert on every call.
key="$session"$'\t'"$tool"$'\t'"$input"
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0
logline() { mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$1" "$2" >> "$log"; }

ctl_session=""
for f in "$HOME"/.claude/sessions/*.json; do
  [ -e "$f" ] || continue
  IFS=$'\t' read -r pid start sid < <(jq -r --arg c "$controller" \
    'select(.name == $c) | "\(.pid)\t\(.procStart // "")\t\(.sessionId // "")"' "$f" 2>/dev/null)
  [[ "${pid:-}" =~ ^[0-9]+$ ]] || continue
  stat="$(cat "/proc/$pid/stat" 2>/dev/null)" || continue
  read -ra fields <<<"${stat##*) }"
  [ -n "$start" ] && [ "${fields[19]:-}" = "$start" ] || continue
  ctl_session="$sid"; break
done

worker_agent="$(timeout 2 herdr agent get "${HERDR_PANE_ID:-}" 2>/dev/null | jq -r '.result.agent.name // empty' 2>/dev/null)"
worker_agent="${worker_agent:-${HERDR_PANE_ID:-unknown pane}}"
alert="[worker-spin-alert] worker #$n repeated $tool $input at least $count times in a row (herdr agent $worker_agent, controller $controller)"

pane=""
[ -n "$ctl_session" ] && pane="$(timeout 2 herdr agent list 2>/dev/null | jq -r --arg s "$ctl_session" \
  '.result.agents[]? | select(.agent_session.value == $s) | .pane_id' 2>/dev/null | head -n1)"
if [ -z "$pane" ]; then logline "not-sent" "no herdr pane for controller $controller: $alert"; exit 0; fi
if out="$(timeout 3 herdr agent prompt "$pane" "$alert" 2>&1)"; then
  logline "sent" "$pane: $alert"
else
  logline "not-sent" "herdr agent prompt $pane failed: $(tr '\n' ' ' <<<"$out")"
fi
exit 0
