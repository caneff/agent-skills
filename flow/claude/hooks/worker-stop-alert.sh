#!/usr/bin/env bash
# Stop hook: tell the controller when a worker stops without reporting (#820).
#
# Contract: read the Stop event JSON on stdin. The session is a worker when its
# transcript opens with an `/implement` or `/implement-spec` brief carrying
# `--controller "<name>"`. A turn starts at a human prompt or a peer message
# that is not a subagent hand-back. The worker has reported when, after that
# turn start, a SendMessage to the controller came back with `success: true`.
# A stop while something launched this turn — or an earlier turn, with
# liveness evidence since this turn's start (#900) — is still out is a wait,
# not a finish. A subagent is "handed back" in one of three shapes: an
# `.origin.senderTaskId` peer message (an anonymous `Agent` call's
# hand-back), a `<task-id>...</task-id>` tag (a task-notification), or a
# named teammate's plain-text `<teammate-message teammate_id="...">` reply
# (#859) — that last shape carries no `origin` at all, and its launch id is
# qualified (`name@session-...`) where the reply's `teammate_id` is bare, so
# matching strips the `@session-...` suffix before comparing. A background
# shell and a Monitor task are out on the same footing (#886), and end only
# at a status-bearing task-notification, a `TaskStop`, or a Monitor timeout
# notification (`<event>[Monitor timed out — re-arm if needed.]</event>`,
# statusless but a finish, not a touch — #981). Also not a silent
# stop: a worker that reported and has done nothing since — an inbound peer
# message starts a turn, so a controller closing its own loop (`merged, sha
# X`) otherwise manufactures an alert on that worker's next stop (#886).
# Otherwise submit one line into the controller's herdr pane
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

# A live registry record naming `sid` (mode "sid") or `nm` (mode "name"),
# with a non-empty `.name` — its session id, current name and socket. Joined
# and split on `\x1f` (ASCII unit separator), not a tab: tab is one of
# bash's default IFS-whitespace characters, so `read` collapses runs of it
# and strips a leading/trailing one regardless of field order — an empty
# `.sessionId` or `.messagingSocketPath` in the middle silently shifted
# every field after it into the wrong variable (verification pass on #981,
# #1014: confirmed against a record with a name and a socket but no
# `.sessionId`). `\x1f` is not IFS-whitespace, so a run of it never
# collapses and an empty field never disappears, whatever position it's in.
# Live means the pid's /proc starttime (field 22, after the `(comm)` field)
# equals the record's procStart — a stale record whose pid was reused has
# another, as in flow/lane's sessions reader.
resolve_session() {
  local mode="$1" val="$2" f pid start sid nm sock stat fields
  for f in "$HOME"/.claude/sessions/*.json; do
    [ -e "$f" ] || continue
    IFS=$'\x1f' read -r pid start sid nm sock < <(jq -r --arg mode "$mode" --arg v "$val" \
      'select((if $mode == "sid" then .sessionId else .name end) == $v and ((.name // "") != "")) |
       [(.pid | tostring), (.procStart // ""), (.sessionId // ""), (.name // ""), (.messagingSocketPath // "")]
       | join("\u001f")' "$f" 2>/dev/null)
    [[ "${pid:-}" =~ ^[0-9]+$ ]] || continue
    stat="$(cat "/proc/$pid/stat" 2>/dev/null)" || continue
    read -ra fields <<<"${stat##*) }"
    [ -n "$start" ] && [ "${fields[19]:-}" = "$start" ] || continue
    printf '%s\x1f%s\x1f%s\n' "$sid" "$nm" "$sock"
    return 0
  done
  return 1
}

# The brief carries the controller's herdr agent name (#923); a compliant
# worker resolves that to a session name or socket before sending, so
# matching on the brief's literal alone can miss a delivered report and,
# when an alert is owed, find no live session for the pane lookup. Resolve
# the same two hops `resolve-controller` does — herdr agent name ->
# `agent_session` id -> the live session record's current name and socket —
# before either use, but keep matching the brief's own literal too: nothing
# here requires a worker to route through `resolve-controller` first, and
# `resolve-controller` itself refuses to resolve a live session with no
# `name` (`sessions::name_of_session`), so a record this can't name is one a
# compliant worker couldn't have addressed either (#1014). A worktree
# without `herdr`, or a `herdr agent list` that fails or times out, falls
# back the same way an older brief already carrying a session name does.
herdr_sid="$(timeout 2 herdr agent list 2>/dev/null \
  | jq -r --arg c "$controller" '.result.agents[]? | select((.name // "") == $c) | .agent_session.value // empty' 2>/dev/null \
  | head -n1)"
resolved=""
[ -n "$herdr_sid" ] && resolved="$(resolve_session sid "$herdr_sid")"
[ -n "$resolved" ] || resolved="$(resolve_session name "$controller")"
ctl_session="" ctl_socket="" resolved_name=""
if [ -n "$resolved" ]; then
  IFS=$'\x1f' read -r ctl_session resolved_name ctl_socket <<<"$resolved"
fi
# The pane lookup needs only a session id, not a name: a live session with
# no `.name` isn't addressable by a compliant worker either way (matching
# already falls back to the brief's literal), but its pane should still be
# found so a genuinely silent stop can alert, rather than end in "no herdr
# pane for controller" — the exact failure #1014 opens with (verification
# pass, P2).
[ -z "$ctl_session" ] && ctl_session="$herdr_sid"

# The verdict for this stop: `reported`, `waiting` on a subagent, or `silent`,
# plus the transcript's last entry as the stop's key. `$c` is the brief's
# literal controller value (a herdr agent name or an already-live session
# name) and `$rn` its resolved session name when resolution found one — a
# report is counted against either, since nothing here requires a worker to
# have resolved before sending (#1014).
IFS=$'\t' read -r verdict stop < <(entries | jq -r --arg c "$controller" --arg rn "$resolved_name" --arg sock "$ctl_socket" '
  to_entries as $all
  | ($all | map(select(.value.type == "user"
      and (.value.origin.kind == "human" or (.value.origin.kind == "peer" and .value.origin.handback != true))))
   | last | .key // 0) as $start
  | .[($start + 1):] as $after
  | [$all[] | select(.value.type == "assistant") | .value.message.content[]?
      | select(.type == "tool_use" and .name == "SendMessage")
      | select(.input.to | strings
          | (. == $c or startswith($c + " [")
             or ($rn != "" and (. == $rn or startswith($rn + " ["))))
             or ($sock != "" and . == "uds:" + $sock))
      | .id] as $sends
  # Every delivered report, by its position in the transcript.
  | [$all[] | select(.value.type == "user" and (.value.toolUseResult | type) == "object"
        and .value.toolUseResult.success == true)
      | select([.value.message.content[]? | select(.type == "tool_result")
                | .tool_use_id | select(IN($sends[]))] | length > 0)
      | .key] as $reports
  | [$reports[] | select(. > $start)] as $delivered
  # An inbound peer message starts a turn, so a controller closing a loop
  # (`merged, sha X`) used to manufacture an alert on the next stop (#886).
  # A report still stands while nothing has happened since it: any tool call
  # or tool result after the last delivered report is work that owes the
  # controller a new one.
  | ($reports | last) as $reported_at
  | [$all[] | select($reported_at != null and .key > $reported_at)
      | select((.value.type == "assistant"
                and ([.value.message.content[]? | select(.type == "tool_use")] | length > 0))
               or (.value.toolUseResult != null))] as $since_report
  # Liveness evidence (#900): a launch from an earlier turn counts as out
  # only if something since the start of this turn names its id — a tool call
  # by the worker whose task_id, shell_id, agentId or `to` is that id (a
  # `BashOutput`/`TaskOutput` poll, a `SendMessage` to the subagent), or a
  # task-notification carrying it without a `<status>` (a Monitor event). A message that arrives while a
  # job is out restarts the turn but not the evidence, so an id nothing has
  # touched since is treated as abandoned, not carried: 45% of launches
  # never emit a terminal notification (docs/research/
  # 2026-09-19-background-task-terminal-states.md), and carrying every one
  # would hold the verdict at `waiting` for the rest of the session. Returns
  # and finishes are read over the whole transcript; an id ends wherever it
  # ends. A launch this turn needs no evidence.
  # A probe counts only once it has an answer: a poll the classifier denied,
  # or one that errored, is a call and not evidence of life.
  | [$after[] | select(.type == "user") | .message.content | arrays[]
      | select(.type == "tool_result" and .is_error != true) | .tool_use_id] as $answered
  # A Monitor timeout notification (exactly `<event>[Monitor timed out —
  # re-arm if needed.]</event>`, no `<status>`) is the monitor stopping, not
  # a tick: it reads a finish, not a touch, or the launch it names stays
  # outstanding across every later turn (#981). Matched on the literal
  # marker inside `<event>`, not a bare substring test, so a monitor whose
  # own tailed output happens to mention "Monitor timed out" in free text
  # is not misread as its own end.
  | [$all[] | .value | select(.type == "user" and .origin.kind == "task-notification")
      | .message.content | strings | select(test("<status>") | not)
      | select(test("<event>\\[Monitor timed out — re-arm if needed\\.\\]</event>"))
      | scan("<task-id>([^<]+)</task-id>")[0]] as $timed_out
  | ([$after[] | select(.type == "assistant") | .message.content[]?
        | select(.type == "tool_use" and (.id | IN($answered[]))) | .input | objects
        | (.task_id, .shell_id, .bash_id, .agentId, .agent_id, .to) | strings]
     + [$after[] | select(.type == "user" and .origin.kind == "task-notification")
        | .message.content | strings | select(test("<status>") | not)
        | scan("<task-id>([^<]+)</task-id>")[0]
        | select(IN($timed_out[]) | not)]) as $touched
  # An id is compared whole, in the fields that name a task or an agent, and
  # never searched for inside free text: an id that merely appears in a
  # command, a written file or a peer message is not evidence of life.
  | def alive: [., sub("@session-[^@]*$"; "")] | any(.[]; IN($touched[]));
  def outstanding($launches; $now): [$launches[] | select(IN($now[]) or alive)] | unique;
  [$all[] | .value | select(.type == "user") | .toolUseResult? | objects
      | select(.status == "async_launched" or .status == "teammate_spawned")
      | (.agentId // .agent_id) | select(strings)] as $launched_all
  | [$after[] | .toolUseResult? | objects
      | select(.status == "async_launched" or .status == "teammate_spawned")
      | (.agentId // .agent_id) | select(strings)] as $launched_now
  | [$all[] | .value | select(.type == "user") | (.origin.senderTaskId // empty),
      (.message.content | strings | scan("<task-id>([^<]+)</task-id>")[0]),
      (.message.content | strings | scan("<teammate-message teammate_id=\"([^\"]+)\"")[0])] as $returned
  | [$all[] | .value | select(.type == "user") | .toolUseResult? | objects
      | (.backgroundTaskId // .taskId) | select(strings)] as $tasks_all
  | [$after[] | .toolUseResult? | objects
      | (.backgroundTaskId // .taskId) | select(strings)] as $tasks_now
  | [($all[] | .value | select(.type == "user") | .message.content | strings
       | select(test("<status>")) | scan("<task-id>([^<]+)</task-id>")[0]),
     $timed_out[],
     ($all[] | .value | select(.type == "assistant") | .message.content[]?
       | select(.type == "tool_use" and .name == "TaskStop")
       | (.input.task_id // .input.shell_id) | select(strings))] as $finished
  | outstanding($tasks_all; $tasks_now) as $tasks
  | ($tasks - $finished) as $unfinished
  # A teammate launch id is qualified (name@session-...); its reply id is
  # bare. Neither form appearing in $returned (both survive the set
  # difference, so the length is 2) means this launch is still unresolved.
  | outstanding($launched_all; $launched_now) as $launched
  | [$launched[] | select(([., sub("@session-[^@]*$"; "")] - $returned | length) == 2)] as $unresolved
  | (if ($delivered | length) > 0 then "reported"
     elif $reported_at != null and ($since_report | length) == 0 then "reported"
     elif (($unresolved | length) + ($unfinished | length)) > 0 then "waiting"
     else "silent" end) as $verdict
  | "\($verdict)\t\(last.uuid // "line \(length)")"')
[ "${verdict:-}" = "silent" ] || exit 0

# One alert per stop: a stop already in the log never alerts again.
key="$session"$'\t'"$stop"
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0

logline() { mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$1" "$2" >> "$log"; }

# Every herdr call below ends by a 10 s deadline, measured from here — not
# 12 s, because the controller resolution above already spent up to its own
# 2 s budget on the same 15 s hook timeout, and this deadline has to leave
# room for that whether or not the stop turned out silent (#1014).
deadline=$((SECONDS + 10))

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
