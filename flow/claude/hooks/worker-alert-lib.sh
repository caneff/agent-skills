# Shared helpers for the two worker alert hooks: the `/implement`
# brief-capture regex, the `~/.claude/sessions/*.json` registry loop with its
# `/proc/<pid>/stat` field-22 liveness check, `logline()`'s format, and the
# herdr agent-name lookup and the controller's socket delivery. Sourced, not executed — the hook
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
# one line per record: its session id, current name (possibly empty),
# socket, pid and procStart (the pid names the record's `<pid>.<hex>.key`,
# and procStart tells that key from a stale one on a reused pid, #1946).
# `sid` mode prints every live match; `name` mode only the first.
# `sid` mode matches on `.sessionId` alone, with no requirement that
# `.name` be non-empty: a Claude session with no name yet is still live,
# still sends and receives cross-session messages (every one carries
# `from="uds:<its socket>"`, and a reply copies that address), and a report
# it delivered to its own socket is real even though it has nothing to
# match by name. Requiring a non-empty name would drop exactly this socket.
# `name` mode still only matches a non-empty `.name` because it matches ON
# that field. Joined and split on `\x1f` (ASCII unit separator), not a tab:
# tab is one of bash's default IFS-whitespace characters, so `read`
# collapses runs of it and strips a leading/trailing one regardless of
# field order — an empty `.sessionId`, `.name` or `.messagingSocketPath` in
# the middle silently shifted every field after it into the wrong variable.
# `\x1f` is not IFS-whitespace, so a run of it never collapses and an empty
# field never disappears, whatever position it's in. Live means the pid's
# /proc starttime (field 22, after the `(comm)` field) equals the record's
# procStart — a stale record whose pid was reused has another, as in
# flow/lane's sessions reader.
worker_alert_resolve_session() { # <mode: sid|name> <val> -> "sid\x1fname\x1fsock\x1fpid\x1fstart" per line on stdout (sid mode: every live match), 0; else 1
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
    printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$sid" "$nm" "$sock" "$pid" "$start"
    found=0
    # `name` mode matches ON a non-empty name: first hit stands. Two live
    # records can share one sessionId (flow/lane's sessions reader scans for
    # the later named one on purpose), and a report to either one's name or
    # socket reached the controller, so `sid` mode prints every live match —
    # neither the named one nor its nameless twin is dropped.
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
# bare pane id, then to "unknown pane".
worker_alert_worker_agent_name() { # -> name
  local n
  n="$(timeout 2 herdr agent get "${HERDR_PANE_ID:-}" 2>/dev/null | jq -r '.result.agent.name // empty' 2>/dev/null)"
  printf '%s\n' "${n:-${HERDR_PANE_ID:-unknown pane}}"
}

# Resolves the brief's controller to the live records that stand for it, the
# two hops `resolve-controller` makes: herdr agent name -> `agent_session`
# id -> live records sharing it, falling back to a live session bearing the
# brief's literal as its name (then widened to its session id). Sets four
# globals for the caller: `herdr_sid` (the herdr hop's session id, or
# empty), the arrays `names` (every live session name) and `sockets` (every
# `uds:` address) a report to the controller could carry, and `ctl_targets`
# (one `pid\x1fsocket\x1fprocStart` entry per live record that has a
# socket, what the delivery connects to). A worktree without `herdr`, or a
# `herdr agent list` that fails or times out, falls back to the literal the
# way an older brief already carrying a session name does.
worker_alert_resolve_controller() { # <controller from the brief> -> sets herdr_sid names sockets ctl_targets
  local controller="$1" resolved="" by_name_sid widened
  local r_sid r_name r_sock r_pid r_start
  herdr_sid="$(timeout 2 herdr agent list 2>/dev/null \
    | jq -r --arg c "$controller" '.result.agents[]? | select((.name // "") == $c) | .agent_session.value // empty' 2>/dev/null \
    | head -n1)"
  [ -n "$herdr_sid" ] && resolved="$(worker_alert_resolve_session sid "$herdr_sid")"
  if [ -z "$resolved" ]; then
    resolved="$(worker_alert_resolve_session name "$controller")"
    # A name resolves one record; widen to every live record sharing its
    # session id, so a nameless twin's socket counts here too.
    by_name_sid="${resolved%%$'\x1f'*}"
    [ -n "$by_name_sid" ] && widened="$(worker_alert_resolve_session sid "$by_name_sid")" \
      && resolved="$widened"
  fi
  # `sid` mode can return several lines: every live record sharing the
  # controller's session id. A report to any of them reached the
  # controller, so every name and socket joins the match set.
  names=() sockets=() ctl_targets=()
  while IFS=$'\x1f' read -r r_sid r_name r_sock r_pid r_start; do
    [ -n "$r_name" ] && names+=("$r_name")
    if [ -n "$r_sock" ]; then
      sockets+=("uds:$r_sock")
      ctl_targets+=("$r_pid"$'\x1f'"$r_sock"$'\x1f'"$r_start")
    fi
  done <<<"$resolved"
  return 0
}

# Writes `alert` to one session's inbox socket as a cross-session peer
# message (#1946), never into a pane: two newline-delimited JSON lines sent
# at once, an `auth` line carrying the `peerToken` of the session's own
# `~/.claude/sessions/<pid>.<hex>.key`, then the `user` message. One write,
# because the receiver closes a connection that sends no complete line
# within its first-line deadline. Python's `json` builds the frame, so
# quotes, backslashes and newlines in the alert stay JSON-safe. A key whose
# `procStart` differs from the live record's belongs to an earlier process
# on a reused pid and is skipped. Claude Code does not document the
# protocol (docs/research/2026-11-21-peer-socket-auth-1946.md). Prints the
# cause and returns 1 on any failure: no usable key file, a missing socket,
# a refused connect or a failed write. An unreadable key is never read as
# "sent". Success means the frame was written: the receiver sends nothing
# back, so a frame it drops (a rotated token, a changed format) still logs
# `sent`; only the live check proves arrival.
worker_alert_send_peer() { # <sock> <pid> <procStart> <alert> -> prints the cause, returns 1 on failure
  timeout 5 python3 -I -c '
import glob, json, os, socket, sys
sock_path, pid, start, alert = sys.argv[1:5]
sessions = os.path.join(os.environ["HOME"], ".claude", "sessions")
def fail(msg):
    print(msg)
    sys.exit(1)
keys = sorted(glob.glob(os.path.join(glob.escape(sessions),
                                     glob.escape(pid) + ".*.key")))
if not keys:
    fail("no key file %s/%s.<hex>.key" % (sessions, pid))
token, why = None, []
for k in keys:
    try:
        with open(k) as f:
            rec = json.load(f)
    except (OSError, ValueError) as e:
        why.append("unreadable key file %s: %s" % (k, e))
        continue
    if not isinstance(rec, dict) or not isinstance(rec.get("peerToken"), str) \
            or not rec["peerToken"]:
        why.append("key file %s has no peerToken" % k)
    elif start and rec.get("procStart") not in (None, start):
        why.append("key file %s is for another process start" % k)
    else:
        token = rec["peerToken"]
        break
if token is None:
    fail("; ".join(why))
if not os.path.exists(sock_path):
    fail("socket %s does not exist" % sock_path)
frame = (json.dumps({"type": "auth", "token": token}) + "\n"
         + json.dumps({"type": "user",
                       "message": {"role": "user", "content": alert}})
         + "\n").encode()
s = socket.socket(socket.AF_UNIX)
s.settimeout(3)
try:
    s.connect(sock_path)
    s.sendall(frame)
except OSError as e:
    fail("socket %s: %s" % (sock_path, e))
finally:
    s.close()
' "$1" "$2" "$3" "$4" 2>&1
}

# The tail both hooks end in: send `alert` to the controller's socket as a
# peer message, trying each entry of the global `ctl_targets` that
# `worker_alert_resolve_controller` set until one takes the frame, and log
# the outcome under `key`. Sets `prompt_status` (`sent` or `not-sent`) and
# `prompt_msg`, the log line's text; a `not-sent` line names every cause.
# A target is tried only while `deadline` (a $SECONDS value) leaves its 5 s
# send room, so twin records cannot run the hook past its own timeout.
worker_alert_deliver() { # <log> <key> <controller> <alert> <deadline in $SECONDS>
  local log="$1" key="$2" controller="$3" alert="$4" deadline="$5"
  local t pid sock start why rc causes="" tried=0
  for t in ${ctl_targets[@]+"${ctl_targets[@]}"}; do
    if [ "$tried" -gt 0 ] && [ $((SECONDS + 5)) -gt "$deadline" ]; then
      causes="${causes:+$causes; }out of time before trying the next socket"
      break
    fi
    tried=$((tried + 1))
    IFS=$'\x1f' read -r pid sock start <<<"$t"
    why="$(worker_alert_send_peer "$sock" "$pid" "$start" "$alert")" && rc=0 || rc=$?
    if [ "$rc" = 0 ]; then
      prompt_status=sent prompt_msg="uds:$sock: $alert"
      worker_alert_logline "$log" "$key" "$prompt_status" "$prompt_msg"
      return 0
    fi
    # A send killed by its timeout or a signal prints nothing: say so.
    [ -n "$why" ] || why="send to $sock failed with exit $rc and no output (timeout 124)"
    causes="${causes:+$causes; }$(tr '\n' ' ' <<<"$why")"
  done
  prompt_status=not-sent
  if [ "$tried" = 0 ]; then
    prompt_msg="no live session record with a messaging socket for controller $controller: $alert"
  else
    prompt_msg="$causes: $alert"
  fi
  worker_alert_logline "$log" "$key" "$prompt_status" "$prompt_msg"
  return 1
}

# The controller a worker reports to now: the name in the latest `Your
# controller is now <name>` peer message (what `controller-adopt` tells a
# worker when its dispatcher's process exited), else the brief's literal.
# Only a peer-origin entry counts, so text a ticket or a web page carried
# into the transcript cannot name a controller.
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
# this function cannot be called; a change to one is a change to both. Its
# sender check (`from_controller`) matches the same names and sockets again.
worker_alert_is_controller_target() { # <to> <brief controller> -> 0 when it is
  local to="$1" nm
  for nm in "$2" ${names[@]+"${names[@]}"} ${sockets[@]+"${sockets[@]}"}; do
    [ "$to" = "$nm" ] && return 0
    [[ "$to" == "$nm ["* ]] && return 0
  done
  return 1
}
