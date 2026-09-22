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
# Spin: the same tool with the same input, N (default 20, SPIN_N) times in a
# row with no other tool call between. "Same" is structural equality of the
# stored input object: the transcript holds the harness's serialization, not
# the bytes the model emitted, so byte equality cannot be tested and key order
# alone never separates two calls. The observed loop ran 180; a retry or a
# sanctioned poll stays in single digits, and a `Monitor` until-loop is one
# call. Only the transcript tail is read, so the per-call cost stays flat and
# `count` is a floor: a longer run reports the window it saw (the last 500
# tool-call lines).
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
  # Bounded read: the last 4 MB, then only lines that carry a tool call. A real
  # transcript holds ~8 lines per call (attachments, system, queue entries,
  # subagent sidechains), so a window counted in raw lines can hold fewer than
  # N calls and read a spin as quiet.
  # run_id: the tool_use id of the earliest call in the current consecutive
  # streak — a run boundary, not just the repeated (name, input). Two spins
  # of the same call, separated by a different tool call, are two streaks
  # with two run_ids, so each alerts once instead of the second being read
  # as a dup of the first (#998).
  tail -c 4000000 "$1" | grep -F '"type":"tool_use"' | tail -n 500 | jq -nRc --argjson n "$N" '
    [inputs | fromjson? | objects | select(.type == "assistant" and .isSidechain != true)
      | .message.content[]? | select(.type == "tool_use") | {name, input, id}] | reverse as $calls
    | ($calls[0] // null) as $l
    | (reduce $calls[] as $c ({n: 0, stop: false, first_id: null};
        if .stop then .
        elif ($l != null and $c.name == $l.name and $c.input == $l.input) then (.n += 1 | .first_id = $c.id)
        else .stop = true end)) as $r
    | {spinning: ($r.n >= $n), tool: ($l.name // null), input: ($l.input // null), count: $r.n, run_id: $r.first_id}'
}

if [ "${1:-}" = "--classify" ]; then
  # An unreadable transcript is not a quiet one: refuse, do not answer "not spinning".
  [ -r "${2:-}" ] || { echo "worker-spin-alert: cannot read transcript '${2:-}'" >&2; exit 2; }
  classify "$2"; exit 0
fi

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
full_input="$(jq -c '.input' <<<"$verdict")"
input="$(cut -c1-120 <<<"$full_input")"   # human-facing text only
digest="$(sha256sum <<<"$full_input" | cut -c1-16)"
count="$(jq -r '.count' <<<"$verdict")"
run_id="$(jq -r '.run_id // ""' <<<"$verdict")"

# One alert per run of repeats: keyed by session, tool, input and the
# streak's run_id (the tool-use id of the first call in it), so a run that
# keeps growing does not re-alert on every call, but a later streak of the
# same call after a different tool call in between — a new run_id — alerts
# again (#998). Only a `sent` line dedupes: an alert that never reached the
# controller is retried on the next call.
key="$session"$'\t'"$tool"$'\t'"$digest"$'\t'"$run_id"
grep -qF -- "$key"$'\t'"sent"$'\t' "$log" 2>/dev/null && exit 0
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
