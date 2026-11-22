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
# socket and pid (the pid names the record's `<pid>.<hex>.key`, #1946). `sid` mode prints every live match; `name` mode only the first.
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
worker_alert_resolve_session() { # <mode: sid|name> <val> -> "sid\x1fname\x1fsock\x1fpid" per line on stdout (sid mode: every live match), 0; else 1
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
    printf '%s\x1f%s\x1f%s\x1f%s\n' "$sid" "$nm" "$sock" "$pid"
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
# brief's literal as its name (then widened to its session id). Sets five
# globals for the caller: `herdr_sid` (the herdr hop's session id, or
# empty), `ctl_session` (the controller's session id), the arrays `names`
# (every live session name) and `sockets` (every `uds:` address) a report to
# the controller could carry, and `ctl_targets` (one `pid\x1fsocket` entry
# per live record that has a socket, what the delivery connects to). A worktree without
# `herdr`, or a `herdr agent list` that fails or times out, falls back to the
# literal the way an older brief already carrying a session name does.
worker_alert_resolve_controller() { # <controller from the brief> -> sets herdr_sid ctl_session names sockets
  local controller="$1" resolved="" by_name_sid widened r_sid r_name r_sock r_pid
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
  # `sid` mode can return several lines — every live record sharing the
  # controller's session id. A report to any of them reached the
  # controller, so every name and socket joins the match set; the session id,
  # the same on every line, is what the pane lookup uses.
  ctl_session="" names=() sockets=() ctl_targets=()
  while IFS=$'\x1f' read -r r_sid r_name r_sock r_pid; do
    [ -n "$ctl_session" ] || ctl_session="$r_sid"
    [ -n "$r_name" ] && names+=("$r_name")
    if [ -n "$r_sock" ]; then
      sockets+=("uds:$r_sock")
      ctl_targets+=("$r_pid"$'\x1f'"$r_sock")
    fi
  done <<<"$resolved"
  # Belt and braces: a record removed between the herdr list and here, while
  # herdr's own bookkeeping still knows the id.
  [ -z "$ctl_session" ] && ctl_session="$herdr_sid"
  return 0
}

# Writes `alert` to one session's inbox socket as a cross-session peer
# message (#1946), never into a pane: two newline-delimited JSON lines sent
# at once, an `auth` line carrying the `peerToken` of the session's own
# `~/.claude/sessions/<pid>.<hex>.key`, then the `user` message. Both lines go
# in one write because the receiver closes a connection that sends no
# complete line within its first-line deadline. The frame is built by Python's
# `json`, so quotes, backslashes and newlines in the alert stay JSON-safe.
# Claude Code does not document this protocol
# (docs/research/2026-11-21-peer-socket-auth-1946.md); a change to it shows as
# a `not-sent` line naming the cause. Prints the cause and returns 1 on any
# failure: no key file, an unreadable key or one without a `peerToken`, a
# missing socket, a refused connect or a failed write. A key that cannot be
# read is never read as "sent". Success means the frame was written: the
# receiver sends nothing back, so acceptance is not observed.
worker_alert_send_peer() { # <sock> <pid> <alert> -> prints the cause and returns 1 on failure
  timeout 5 python3 -I -c '
import glob, json, os, socket, sys
sock_path, pid, alert = sys.argv[1:4]
sessions = os.path.join(os.environ["HOME"], ".claude", "sessions")
def fail(msg):
    print(msg); sys.exit(1)
keys = sorted(glob.glob(os.path.join(glob.escape(sessions), glob.escape(pid) + ".*.key")))
if not keys:
    fail("no key file %s/%s.<hex>.key" % (sessions, pid))
token = None
for k in keys:
    try:
        with open(k) as f:
            rec = json.load(f)
    except (OSError, ValueError) as e:
        fail("unreadable key file %s: %s" % (k, e))
    if isinstance(rec, dict) and isinstance(rec.get("peerToken"), str) and rec["peerToken"]:
        token = rec["peerToken"]
        break
if token is None:
    fail("key file %s has no peerToken" % keys[0])
if not os.path.exists(sock_path):
    fail("socket %s does not exist" % sock_path)
frame = (json.dumps({"type": "auth", "token": token}) + "\n"
         + json.dumps({"type": "user", "message": {"role": "user", "content": alert}}) + "\n").encode()
s = socket.socket(socket.AF_UNIX)
s.settimeout(3)
try:
    s.connect(sock_path)
    s.sendall(frame)
except OSError as e:
    fail("socket %s: %s" % (sock_path, e))
finally:
    s.close()
' "$1" "$2" "$3" 2>&1 || return 1
}

# The tail both hooks end in: send `alert` to the controller's socket as a
# peer message from the global `ctl_targets` that
# `worker_alert_resolve_controller` set, and log the outcome under `key`. Tries
# each live record that has a socket until one takes the frame. Sets
# `prompt_status` (`sent` or `not-sent`) and `prompt_msg`, the log line's text;
# a `not-sent` line names every cause. `deadline` is unused, kept so the
# callers' signature stays one (the retry on a blocked pane went with the pane).
worker_alert_deliver() { # <log> <key> <controller> <alert> <deadline in $SECONDS>
  local log="$1" key="$2" controller="$3" alert="$4" t pid sock why causes=""
  for t in ${ctl_targets[@]+"${ctl_targets[@]}"}; do
    pid="${t%%$'\x1f'*}" sock="${t#*$'\x1f'}"
    if why="$(worker_alert_send_peer "$sock" "$pid" "$alert")"; then
      prompt_status=sent prompt_msg="uds:$sock: $alert"
      worker_alert_logline "$log" "$key" "$prompt_status" "$prompt_msg"
      return 0
    fi
    causes="${causes:+$causes; }$(tr '\n' ' ' <<<"$why")"
  done
  prompt_status=not-sent
  if [ -z "$causes" ]; then
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
