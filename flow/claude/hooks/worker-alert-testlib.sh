# Shared fixtures for the worker-alert hook tests (#1946). Sourced, not run.
# A fake controller inbox: a listening Unix socket that writes every
# connection's bytes, read to EOF, to <dir>/frames/<seq>.

# wa_start_inbox <dir> <name> -> sets wa_sock and wa_server_pid; the caller's
# EXIT trap kills wa_server_pid (kill_inboxes does it for every inbox started).
wa_server_pids=()
wa_start_inbox() {
  local dir=$1 name=$2 i
  mkdir -p "$dir"
  cat > "$dir/server.py" <<'PY'
import os, socket, sys
path, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
srv = socket.socket(socket.AF_UNIX); srv.bind(path); srv.listen(8)
open(path + ".ready", "w").close()
seq = 0
while True:
    c, _ = srv.accept(); c.settimeout(5); buf = b""
    try:
        while True:
            d = c.recv(65536)
            if not d: break
            buf += d
    except OSError: pass
    seq += 1
    tmpf = os.path.join(out, "tmp"); open(tmpf, "wb").write(buf)
    os.rename(tmpf, os.path.join(out, str(seq)))
    c.close()
PY
  wa_sock="$dir/$name.sock"
  python3 "$dir/server.py" "$wa_sock" "$dir/frames" & wa_server_pid=$!
  wa_server_pids+=("$wa_server_pid")
  for i in $(seq 100); do [ -e "$wa_sock.ready" ] && break; sleep 0.05; done
}
kill_inboxes() { local p; for p in ${wa_server_pids[@]+"${wa_server_pids[@]}"}; do kill "$p" 2>/dev/null; done; }

# wa_newest <dir> -> the newest frame file of that inbox, or nothing.
wa_newest() { ls "$1/frames" 2>/dev/null | grep '^[0-9]' | sort -n | tail -1 | sed "s|^|$1/frames/|"; }
# wa_frames <dir> -> how many frames it holds.
wa_frames() { ls "$1/frames" 2>/dev/null | grep -c '^[0-9]'; }
# wa_wait_frame <dir> -> 0 once a frame is there, 1 after about 3 s.
wa_wait_frame() { local i; for i in $(seq 60); do [ "$(wa_frames "$1")" -ge 1 ] && return 0; sleep 0.05; done; return 1; }
# wa_text <dir> -> the alert text of the newest frame (its second line).
wa_text() { local f; f=$(wa_newest "$1"); [ -n "$f" ] && sed -n 2p "$f" | jq -r '.message.content' 2>/dev/null; }

# wa_sent_lines <log> -> how many `sent` lines the alert log holds.
wa_sent_lines() { local c; c=$(grep -c $'\tsent\t' "$1" 2>/dev/null); echo "${c:-0}"; }
# wa_dead_socket <path> -> a socket file nobody listens on.
wa_dead_socket() { python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.close()' "$1"; }
# wa_record <sessions dir> <pid> <procStart> <sock> -> the controller's live
# session record for that pid, named skills-b6.
wa_record() {
  printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-b6","messagingSocketPath":"%s"}\n' "$2" "$3" "$4" > "$1/$2.json"
}
# wa_key <sessions dir> <pid> [json] -> publishes <pid>.<64 hex>.key.
wa_key() {
  local hex; hex=$(printf 'a%.0s' $(seq 64))
  printf '%s\n' "${3:-{\"peerToken\":\"0123456789abcdef0123456789abcdef\"\}}" > "$1/$2.$hex.key"
}
