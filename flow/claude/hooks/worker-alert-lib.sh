# Shared helpers for worker-stop-alert.sh (#991): the `/implement`
# brief-capture regex, the `~/.claude/sessions/*.json` registry loop with its
# `/proc/<pid>/stat` field-22 liveness check, `logline()`'s format, and the
# herdr agent-name and pane lookup. Sourced, not executed — the hook
# `source`s this file so a registry schema change or a brief-format change is
# one edit. The hook keeps its own alert text and dedupe key; only these four
# pieces live here.

# The brief: ticket number and controller name from a transcript's first
# human message naming an /implement or /implement-spec command, or nothing
# for a non-worker transcript.
worker_alert_read_brief() { # <transcript> -> "n\tcontroller" on stdout, or empty
  jq -nc '[inputs | fromjson? | objects]' -R "$1" 2>/dev/null | jq -r '
    [.[] | select(.type == "user" and .origin.kind == "human")
         | .message.content | strings
         | capture("<command-name>/implement(-spec)?</command-name>\\s*<command-args>(?<n>[0-9]+)\\b[^<]*--controller \"(?<c>[^\"]+)\"")]
    | first // empty | "\(.n)\t\(.c)"'
}

# Live registry records naming `sid` (mode "sid") or `nm` (mode "name") —
# one line per record: its session id, current name (possibly empty) and
# socket. `sid` mode prints every live match (#1114); `name` mode only the
# first. `sid` mode
# matches on `.sessionId` alone, with no requirement that `.name` be
# non-empty: a Claude session with no name yet is still live, still sends
# and receives cross-session messages (every one carries `from="uds:<its
# socket>"`, and a reply copies that address), and a report it delivered to
# its own socket is real even though it has nothing to match by name
# (Codex pass on PR #1057 — an earlier version of this filter required a
# non-empty name unconditionally and dropped exactly this socket). `name`
# mode still only matches a non-empty `.name` because it matches ON that
# field. Joined and split on `\x1f` (ASCII unit separator), not a tab: tab
# is one of bash's default IFS-whitespace characters, so `read` collapses
# runs of it and strips a leading/trailing one regardless of field order —
# an empty `.sessionId`, `.name` or `.messagingSocketPath` in the middle
# silently shifted every field after it into the wrong variable
# (verification pass on #981, #1014). `\x1f` is not IFS-whitespace, so a
# run of it never collapses and an empty field never disappears, whatever
# position it's in. Live means the pid's /proc starttime (field 22, after
# the `(comm)` field) equals the record's procStart — a stale record whose
# pid was reused has another, as in flow/lane's sessions reader.
worker_alert_resolve_session() { # <mode: sid|name> <val> -> "sid\x1fname\x1fsock" per line on stdout (sid mode: every live match), 0; else 1
  local mode="$1" val="$2" f pid start sid nm sock stat fields found=1
  for f in "$HOME"/.claude/sessions/*.json; do
    [ -e "$f" ] || continue
    IFS=$'\x1f' read -r pid start sid nm sock < <(jq -r --arg mode "$mode" --arg v "$val" \
      'select((if $mode == "sid" then .sessionId else .name end) == $v) |
       [(.pid | tostring), (.procStart // ""), (.sessionId // ""), (.name // ""), (.messagingSocketPath // "")]
       | join("\u001f")' "$f" 2>/dev/null)
    [[ "${pid:-}" =~ ^[0-9]+$ ]] || continue
    stat="$(cat "/proc/$pid/stat" 2>/dev/null)" || continue
    read -ra fields <<<"${stat##*) }"
    [ -n "$start" ] && [ "${fields[19]:-}" = "$start" ] || continue
    printf '%s\x1f%s\x1f%s\n' "$sid" "$nm" "$sock"
    found=0
    # `name` mode matches ON a non-empty name: first hit stands. Two live
    # records can share one sessionId (flow/lane's sessions reader scans for
    # the later named one on purpose), and a report to either one's name or
    # socket reached the controller, so `sid` mode prints every live match —
    # neither the named one (#1059) nor its nameless twin (#1114) dropped.
    [ "$mode" = name ] && return 0
  done
  return "$found"
}

# One alert-log line, in every hook's shared format: date, the caller's key
# (already tab-joined), status, message.
worker_alert_logline() { # <log> <key> <status> <message>
  local log="$1" key="$2" status="$3" msg="$4"
  mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$status" "$msg" >> "$log"
}

# This worker's own herdr agent name, via its pane id — falling back to the
# bare pane id, then to "unknown pane", exactly as the hook did inline.
worker_alert_worker_agent_name() { # -> name
  local n
  n="$(timeout 2 herdr agent get "${HERDR_PANE_ID:-}" 2>/dev/null | jq -r '.result.agent.name // empty' 2>/dev/null)"
  printf '%s\n' "${n:-${HERDR_PANE_ID:-unknown pane}}"
}

# The herdr pane id for a live session id, or empty (including when
# ctl_session itself is empty).
worker_alert_controller_pane() { # <ctl_session> -> pane_id or empty
  local ctl_session="$1"
  [ -n "$ctl_session" ] || return 0
  timeout 2 herdr agent list 2>/dev/null | jq -r --arg s "$ctl_session" \
    '.result.agents[]? | select(.agent_session.value == $s) | .pane_id' 2>/dev/null | head -n1
}

# Resolves the brief's controller to the live records that stand for it, the
# two hops `resolve-controller` makes (#923): herdr agent name -> `agent_session`
# id -> live records sharing it, falling back to a live session bearing the
# brief's literal as its name (then widened to its session id, #1114). Sets
# four globals for the caller: `herdr_sid` (the herdr hop's session id, or
# empty), `ctl_session` (the controller's session id, for the pane lookup),
# and the arrays `names` (every live session name) and `sockets` (every
# `uds:` address) a report to the controller could carry. A worktree without
# `herdr`, or a `herdr agent list` that fails or times out, falls back to the
# literal the way an older brief already carrying a session name does.
worker_alert_resolve_controller() { # <controller from the brief> -> sets herdr_sid ctl_session names sockets
  local controller="$1" resolved="" by_name_sid widened r_sid r_name r_sock
  herdr_sid="$(timeout 2 herdr agent list 2>/dev/null \
    | jq -r --arg c "$controller" '.result.agents[]? | select((.name // "") == $c) | .agent_session.value // empty' 2>/dev/null \
    | head -n1)"
  [ -n "$herdr_sid" ] && resolved="$(worker_alert_resolve_session sid "$herdr_sid")"
  if [ -z "$resolved" ]; then
    resolved="$(worker_alert_resolve_session name "$controller")"
    # A name resolves one record; widen to every live record sharing its
    # session id, so a nameless twin's socket counts here too (#1114).
    by_name_sid="${resolved%%$'\x1f'*}"
    [ -n "$by_name_sid" ] && widened="$(worker_alert_resolve_session sid "$by_name_sid")" \
      && resolved="$widened"
  fi
  # `sid` mode can return several lines — every live record sharing the
  # controller's session id (#1114). A report to any of them reached the
  # controller, so every name and socket joins the match set; the session id,
  # the same on every line, is what the pane lookup uses.
  ctl_session="" names=() sockets=()
  while IFS=$'\x1f' read -r r_sid r_name r_sock; do
    [ -n "$ctl_session" ] || ctl_session="$r_sid"
    [ -n "$r_name" ] && names+=("$r_name")
    [ -n "$r_sock" ] && sockets+=("uds:$r_sock")
  done <<<"$resolved"
  # Belt and braces: a record removed between the herdr list and here, while
  # herdr's own bookkeeping still knows the id.
  [ -z "$ctl_session" ] && ctl_session="$herdr_sid"
  return 0
}

# Submits `alert` into herdr pane `pane` with `herdr agent prompt`. herdr
# refuses a prompt to a blocked agent (`agent_blocked`) before sending any
# input, so that refusal is retried with backoff while `deadline` (a $SECONDS
# value) allows. Sets `prompt_status` (`sent` or `not-sent`) and `prompt_msg`,
# the alert-log line's text; returns 0 only when sent.
worker_alert_prompt_pane() { # <pane> <alert> <deadline in $SECONDS> -> sets prompt_status prompt_msg
  local pane="$1" alert="$2" deadline="$3" attempts=0 backoff=1 out blocked=""
  while :; do
    attempts=$((attempts + 1))
    if out="$(timeout 3 herdr agent prompt "$pane" "$alert" 2>&1)"; then
      prompt_status=sent prompt_msg="$pane: $alert"
      return 0
    fi
    blocked="$(jq -r 'select(.error.code == "agent_blocked") | "yes"' <<<"$out" 2>/dev/null)"
    [ "$blocked" = yes ] && [ $((SECONDS + backoff + 3)) -le "$deadline" ] || break
    sleep "$backoff"
    backoff=$((backoff * 2))
  done
  prompt_status=not-sent
  if [ "$blocked" = yes ]; then
    prompt_msg="controller blocked: herdr agent prompt $pane refused agent_blocked on all $attempts attempts: $alert"
  else
    prompt_msg="herdr agent prompt $pane failed: $(tr '\n' ' ' <<<"$out")"
  fi
  return 1
}

# The controller a worker reports to now: the name in the latest `Your
# controller is now <name>` peer message (what `controller-adopt` tells a
# worker when its dispatcher's process exited, #1098), else the brief's
# literal. Only a peer-origin entry counts, so text a ticket or a web page
# carried into the transcript cannot name a controller.
worker_alert_current_controller() { # <transcript> <brief controller> -> name on stdout
  local adopted
  adopted="$(jq -nc '[inputs | fromjson? | objects]' -R "$1" 2>/dev/null | jq -r '
    [.[] | select(.type == "user" and .origin.kind == "peer") | .message.content
         | if type == "string" then . else ([.[]? | .text? // empty] | join("\n")) end
         | capture("Your controller is now (?<c>[A-Za-z0-9_-]+)") | .c]
    | last // empty' 2>/dev/null)"
  printf '%s\n' "${adopted:-$2}"
}

# Whether a SendMessage `to` addresses the controller: the brief's literal
# (`$2`), a name or a `uds:` address `worker_alert_resolve_controller` left in
# `names` and `sockets`, each optionally followed by SendMessage's ` [ref]`.
# worker-stop-alert.sh reads the same rule in jq over the transcript, where
# this function cannot be called; a change to one is a change to both.
worker_alert_is_controller_target() { # <to> <brief controller> -> 0 when it is
  local to="$1" nm
  for nm in "$2" ${names[@]+"${names[@]}"} ${sockets[@]+"${sockets[@]}"}; do
    [ "$to" = "$nm" ] && return 0
    [[ "$to" == "$nm ["* ]] && return 0
  done
  return 1
}
