# Shared helpers for worker-stop-alert.sh and worker-spin-alert.sh (#991): the
# `/implement` brief-capture regex, the `~/.claude/sessions/*.json` registry
# loop with its `/proc/<pid>/stat` field-22 liveness check, `logline()`'s
# format, and the herdr agent-name and pane lookup. Sourced, not executed —
# both hooks `source` this file so a registry schema change or a brief-format
# change fixes both instead of leaving one resolving no controller and
# exiting 0 silently. Each hook keeps its own alert text and dedupe key; only
# these four pieces live here.

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

# A live registry record naming `sid` (mode "sid") or `nm` (mode "name") —
# its session id, current name (possibly empty) and socket. `sid` mode
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
worker_alert_resolve_session() { # <mode: sid|name> <val> -> "sid\x1fname\x1fsock" on stdout, 0; else 1
  local mode="$1" val="$2" f pid start sid nm sock stat fields
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
    return 0
  done
  return 1
}

# One alert-log line, in every hook's shared format: date, the caller's key
# (already tab-joined), status, message.
worker_alert_logline() { # <log> <key> <status> <message>
  local log="$1" key="$2" status="$3" msg="$4"
  mkdir -p "$(dirname "$log")" && printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$key" "$status" "$msg" >> "$log"
}

# This worker's own herdr agent name, via its pane id — falling back to the
# bare pane id, then to "unknown pane", exactly as both hooks did inline.
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
