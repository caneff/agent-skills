#!/usr/bin/env bash
# Stop hook: tell the controller when a worker stops without reporting.
#
# Contract: read the Stop event JSON on stdin. The session is a worker when its
# transcript opens with an `/implement` or `/implement-spec` brief carrying
# `--controller "<name>"`. A turn starts at a human prompt or a peer message
# from the controller (a message from any other session, such as a worker this
# worker dispatched, starts none). The worker has reported when, after that
# turn start, a SendMessage to the controller came back with `success: true`.
# A stop while something launched this turn — or an earlier turn, with
# liveness evidence since this turn's start — is still out is a wait, not
# a finish. A subagent is "handed back" in one of three shapes: an
# `.origin.senderTaskId` peer message (an anonymous `Agent` call's
# hand-back), a `<task-id>...</task-id>` tag (a task-notification), or a
# named teammate's plain-text `<teammate-message teammate_id="...">` reply
# — that last shape carries no `origin` at all, and its launch id is
# qualified (`name@session-...`) where the reply's `teammate_id` is bare, so
# matching strips the `@session-...` suffix before comparing. A background
# shell and a Monitor task are out on the same footing, and end only at a
# status-bearing task-notification, a `TaskStop`, or a Monitor timeout
# notification (`<event>[Monitor timed out — re-arm if needed.]</event>`,
# statusless but a finish, not a touch). Also not a silent stop: a worker
# that reported and has done nothing since — an inbound controller message
# starts a turn, so a controller closing its own loop (`merged, sha X`)
# otherwise manufactures an alert on that worker's next stop. Two more waits
# (#1960): a subagent's interim notice (`completed`, summary "is waiting on
# its own background work") is not its hand-back, and a worker whose last
# delivered send is an open request ("ready for seam", a question) that the
# controller has only held ("wait: ... you're next") is waiting for its "go".
# Otherwise submit one line into the controller's herdr pane with `herdr agent
# prompt` — a hook command, so the auto-mode classifier never sees it (a
# report sent that way was once denied there). One alert per stop: every
# attempt is logged to ~/.claude/worker-stop-alerts.log keyed by session
# and the transcript's last entry, and a logged stop never alerts again.
# Always exit 0 — a hook failure must never block the worker's own stop.

set -u

# Through the symlink: install.sh links this hook into ~/.claude/hooks/, and a
# lib looked for beside the link goes missing whenever install.sh has not
# been re-run since the lib was added, and every stop then logs
# lib-missing.
hook_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
log="$HOME/.claude/worker-stop-alerts.log"
lib_missing() { # <what's wrong> -> logs and exits 0, no lib functions required
  mkdir -p "$(dirname "$log")"
  printf '%s\t%s\tnot-sent\t%s\n' "$(date -u +%FT%TZ)" "lib-missing" "$1" >> "$log"
  exit 0
}
# A missing lib (an installed hook whose sibling was never deployed) must not
# join the "not a worker transcript" exit 0 below via a bare command-not-found
# on stderr — that is exactly the silent-exit-0 hazard the shared lib
# exists to fix, one layer up. Logged so a run of missing alerts has a
# trace to find.
source "$hook_dir/worker-alert-lib.sh" 2>/dev/null || \
  lib_missing "missing $hook_dir/worker-alert-lib.sh — hook cannot resolve a controller"
# A lib that parses but is missing a symbol this hook calls (truncated, or
# mid-edit skew between the symlinked hook and its sibling) passes the
# `source` above; every worker_alert_* call after it is then
# command-not-found under `set -u` alone (no `-e`), silently reaching the
# same "not a worker transcript" exit 0 — including the log line itself,
# since worker_alert_logline can be exactly the missing symbol. Checked here
# with `lib_missing`, which needs none of them.
for fn in worker_alert_read_brief worker_alert_resolve_session worker_alert_logline \
          worker_alert_worker_agent_name worker_alert_controller_pane \
          worker_alert_resolve_controller worker_alert_prompt_pane \
          worker_alert_current_controller worker_alert_deliver; do
  declare -F "$fn" >/dev/null || lib_missing "$hook_dir/worker-alert-lib.sh loaded but does not define $fn"
done

event="$(cat)"

jq -e '.stop_hook_active != true' >/dev/null 2>&1 <<<"$event" || exit 0
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
session="$(jq -r '.session_id // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

# Transcript entries, skipping any line that does not parse (a line the
# harness is still writing).
entries() { jq -nc '[inputs | fromjson? | objects]' -R "$transcript" 2>/dev/null; }

# The brief: ticket number and controller name, or nothing for a non-worker.
IFS=$'\t' read -r n controller < <(worker_alert_read_brief "$transcript")
[ -n "${controller:-}" ] || exit 0

# The brief carries the controller's herdr agent name; a compliant worker
# resolves that to a session name or socket before sending, so matching
# on the brief's literal alone can miss a delivered report. Resolve the
# same two hops `resolve-controller` does, but keep matching the brief's
# own literal too: nothing here requires a worker to route through
# `resolve-controller` first. (`worker_alert_resolve_controller`'s comment
# holds the hops and why a nameless record counts.)
controller="$(worker_alert_current_controller "$transcript" "$controller")"

# `drain` is no session: drain's briefs name it on purpose and drain watches
# the pane itself (its idle grace and wall clock, `drain/drain.py`), so there
# is nobody to alert and no pane to look up (#1945). Logged once per session,
# so the log says why and does not fill with a `not-sent` per stop.
if [ "$controller" = drain ]; then
  dkey="$session"$'\t'"drain"
  grep -qF -- "$dkey"$'\t' "$log" 2>/dev/null \
    || worker_alert_logline "$log" "$dkey" skipped "controller drain: drain watches the pane, so no alert is sent"
  exit 0
fi

worker_alert_resolve_controller "$controller"

# The verdict for this stop: `reported`, `waiting` on a subagent, or `silent`,
# plus the transcript's last entry as the stop's key. `$c` is the brief's
# literal controller value (a herdr agent name or an already-live session
# name), `$names` every resolved session name and `$socks` every resolved
# `uds:` address — a report is counted against any of them, since nothing
# here requires a worker to have resolved before sending.
IFS=$'\t' read -r verdict stop turn < <(entries | jq -r --arg c "$controller" \
  --argjson names "$(jq -nc '$ARGS.positional' --args -- ${names[@]+"${names[@]}"})" \
  --argjson socks "$(jq -nc '$ARGS.positional' --args -- ${sockets[@]+"${sockets[@]}"})" '
  # A peer message starts a turn only when the brief'"'"'s controller sent it: a
  # worker that dispatches workers of its own hears from them, and each of
  # those would otherwise start a turn owing the controller a report (#1945).
  # The sender is `.origin.from` (a `uds:` address) and `.origin.name`; both
  # are matched against what `worker_alert_resolve_controller` resolved, the
  # same names and sockets a report is matched against. A peer message
  # carrying neither is attributable to no one, so it starts no turn.
  def from_controller: (.origin.from | IN($socks[])) or (.origin.name | IN($c, $names[]));
  # A sub-worker'"'"'s own stop alert is typed into this pane as a human prompt;
  # it is that worker'"'"'s report to us, not a turn we owe the controller.
  def msg_text: .message.content
      | if type == "string" then . else ([.[]? | .text? // empty] | join("")) end;
  def worker_alert: msg_text | startswith("[worker-stop-alert]");
  # A subagent'"'"'s interim task-notification: status `completed`, but the
  # agent is itself waiting on background work and delivers its report later
  # under the same task-id (#1960). Evidence it is alive, never a return.
  def interim: strings | test("<summary>[^<]*is waiting on its own background work");
  to_entries as $all
  | ($all | map(select(.value.type == "user"
      and ((.value.origin.kind == "human" and (.value | worker_alert | not))
           or (.value.origin.kind == "peer" and .value.origin.handback != true
               and (.value | from_controller)))))
   | last | .key // 0) as $start
  | .[($start + 1):] as $after
  | [$all[] | select(.value.type == "assistant") | .value.message.content[]?
      | select(.type == "tool_use" and .name == "SendMessage")
      | select(.input.to | strings | . as $to
          | any(($c, $names[]); . as $nm | $to == $nm or ($to | startswith($nm + " [")))
            or IN($socks[]))
      | .id] as $sends
  # Every delivered report, by its position in the transcript.
  | [$all[] | select(.value.type == "user" and (.value.toolUseResult | type) == "object"
        and .value.toolUseResult.success == true)
      | select([.value.message.content[]? | select(.type == "tool_result")
                | .tool_use_id | select(IN($sends[]))] | length > 0)
      | .key] as $reports
  | [$reports[] | select(. > $start)] as $delivered
  # An inbound controller message starts a turn, so a controller closing a loop
  # (`merged, sha X`) used to manufacture an alert on the next stop. A
  # report still stands while nothing has happened since it: any tool
  # call or tool result after the last delivered report is work that owes
  # the controller a new one.
  | ($reports | last) as $reported_at
  | [$all[] | select($reported_at != null and .key > $reported_at)
      | select((.value.type == "assistant"
                and ([.value.message.content[]? | select(.type == "tool_use")] | length > 0))
               or (.value.toolUseResult != null))] as $since_report
  # Holding for the controller (#1960): the last delivered send is an open
  # request (it opens with "ready for seam" or ends in "?") and the latest
  # turn-starting message since, from the controller or a human prompt, is a
  # hold ("wait: ... you'"'"'re next"). Ending the turn then is waiting for the
  # promised "go" or ruling. No message since, or any other one (a "go", a
  # ruling, a human prompt), means the request was answered or never held,
  # and a stop with nothing sent is silent.
  | ([$all[] | select(.key == $reported_at) | .value.message.content[]?
      | select(.type == "tool_result") | .tool_use_id | select(IN($sends[]))]
      | first) as $last_id
  | ([$all[] | .value | select(.type == "assistant") | .message.content[]?
      | select(.type == "tool_use" and .id == $last_id)
      | .input.message | if type == "string" then . else tojson end]
      | first // "") as $last_sent
  | ([$all[] | select(.key > $reported_at)
      | .value | select(.type == "user"
          and ((.origin.kind == "human" and (worker_alert | not))
               or (.origin.kind == "peer" and .origin.handback != true
                   and from_controller)))
      | msg_text] | last // "") as $last_starter
  | ($last_id != null
      and ($last_sent | test("^\\s*ready for seam|\\?\\s*$"; "i"))
      and ($last_starter | test("^\\s*(wait|hold)\\s*:"; "i"))
      and ($last_starter | test("\\bgo\\b"; "i") | not)) as $holding
  # Liveness evidence: a launch from an earlier turn counts as out only
  # if something since the start of this turn names its id — a tool call
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
  # outstanding across every later turn. Matched on the literal marker
  # inside `<event>`, not a bare substring test, so a monitor whose own
  # tailed output happens to mention "Monitor timed out" in free text is
  # not misread as its own end.
  | [$all[] | .value | select(.type == "user" and .origin.kind == "task-notification")
      | .message.content | strings | select(test("<status>") | not)
      | select(test("<event>\\[Monitor timed out — re-arm if needed\\.\\]</event>"))
      | scan("<task-id>([^<]+)</task-id>")[0]] as $timed_out
  | ([$after[] | select(.type == "assistant") | .message.content[]?
        | select(.type == "tool_use" and (.id | IN($answered[]))) | .input | objects
        | (.task_id, .shell_id, .bash_id, .agentId, .agent_id, .to) | strings]
     + [$after[] | select(.type == "user" and .origin.kind == "task-notification")
        | .message.content | strings | select((test("<status>") | not) or interim)
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
      (.message.content | select(interim | not) | strings | scan("<task-id>([^<]+)</task-id>")[0]),
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
     elif $holding then "waiting"
     else "silent" end) as $verdict
  | "\($verdict)\t\(last.uuid // "line \(length)")\t\($all[$start].value.uuid // "line \($start)")"')
[ "${verdict:-}" = "silent" ] || exit 0

# One alert per stop: a stop already in the log never alerts again.
key="$session"$'\t'"$stop"
grep -qF -- "$key"$'\t' "$log" 2>/dev/null && exit 0

# And one per turn (#1945): a turn that already sent its alert stays quiet for
# its later stops, a backstop against any misread that leaves several stops
# in one turn. Only a `sent` line counts, so a delivery that failed is tried
# again at the next stop. The turn is the id of the entry that started it,
# the fourth field of the log line (date, session, stop, turn, status, text).
awk -F'\t' -v s="$session" -v t="turn=$turn" '$2 == s && $4 == t && $5 == "sent" { f = 1 } END { exit !f }' \
  "$log" 2>/dev/null && exit 0

# A worker waiting on workers it dispatched through herdr is waiting, not
# stopped (#1945): every `agent:` line of an `implement-dispatch` report in
# this transcript names one, and an agent still in `herdr agent list` is
# alive (merge-cleanup closes its pane when it lands). A list that cannot be
# read names nobody alive, so the stop is judged as it was before: silent.
dispatched="$(entries | jq -r '.[] | select(.type == "user") | .toolUseResult? | objects
  | .stdout? | strings | select(test("(^|\n)dispatched "))
  | split("\n")[] | capture("^agent:\\s+(?<a>\\S+)\\s*$") | .a' 2>/dev/null)"
if [ -n "$dispatched" ]; then
  live="$(timeout 2 herdr agent list 2>/dev/null | jq -r '.result.agents[]? | .name // empty' 2>/dev/null)"
  [ -n "$live" ] && grep -qxFf <(printf '%s\n' "$dispatched") <<<"$live" && exit 0
fi

# Every herdr call below ends by a 10 s deadline, measured from here — not
# 12 s, because the controller resolution above already spent up to its own
# 2 s budget on the same 15 s hook timeout, and this deadline has to leave
# room for that whether or not the stop turned out silent.
deadline=$((SECONDS + 10))

worker_agent="$(worker_alert_worker_agent_name)"
alert="[worker-stop-alert] worker #$n stopped without reporting to $controller (herdr agent $worker_agent)"

worker_alert_deliver "$log" "$key"$'\t'"turn=$turn" "$controller" "$alert" "$deadline"
exit 0
