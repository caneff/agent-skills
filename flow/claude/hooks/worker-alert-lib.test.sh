#!/usr/bin/env bash
# Contract test for worker_alert_deliver's socket delivery (#1946): the alert
# goes to the controller's inbox socket as two newline-delimited JSON lines
# (auth, then the user message), the token read from the controller's own
# `<pid>.<hex>.key`, and nothing is typed into any pane. Runs against a fake
# listening Unix socket; no real session is touched.
# Run: bash flow/claude/hooks/worker-alert-lib.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tmp=$(mktemp -d)

# herdr stub: an empty agent list, and any `agent prompt` is recorded — the
# delivery must never call it.
mkdir -p "$tmp/bin"
cat > "$tmp/bin/herdr" <<STUB
#!/usr/bin/env bash
case "\$1 \$2" in
  "agent list") echo '{"result":{"agents":[]}}' ;;
  "agent prompt") echo "\$*" >> "$tmp/prompt.called" ;;
esac
STUB
chmod +x "$tmp/bin/herdr"

. "$here/worker-alert-testlib.sh"
trap 'kill_inboxes; rm -rf "$tmp"' EXIT
wa_start_inbox "$tmp/inbox" ctl
sock="$wa_sock"

home="$tmp/home"; sessions="$home/.claude/sessions"
mkdir -p "$sessions"
start=$(stat=$(cat /proc/$$/stat); set -- ${stat##*) }; echo "${20}")
token="0123456789abcdef0123456789abcdef"
record() { printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","name":"skills-b6","messagingSocketPath":"%s"}\n' "$$" "$start" "$1" > "$sessions/$$.json"; }
keyfile() { wa_key "$sessions" "$$" "$1"; }
record "$sock"; keyfile "{\"peerToken\":\"$token\",\"procStart\":\"$start\",\"pidDomain\":\"x\"}"
log="$home/.claude/alerts.log"

fails=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; fails=1; }

# deliver <alert> -> sets $rc, $status, $msg in this shell
deliver() {
  rm -rf "$tmp/inbox/frames"/[0-9]* "$log" "$tmp/prompt.called"
  (
    export HOME="$home" PATH="${extra_path:+$extra_path:}$tmp/bin:$PATH"
    source "$here/worker-alert-lib.sh"
    worker_alert_resolve_controller skills-b6
    worker_alert_deliver "$log" "k1" skills-b6 "$1" ${deadline_s:-$((SECONDS + 10))}
    echo $? > "$tmp/rc"; printf '%s' "$prompt_status" > "$tmp/status"; printf '%s' "$prompt_msg" > "$tmp/msg"
  )
  rc=$(cat "$tmp/rc"); status=$(cat "$tmp/status"); msg=$(cat "$tmp/msg")
}

# 1. Delivery: exactly the two JSON lines, token from the key file.
alert='[worker-stop-alert] worker #1 stopped'
deliver "$alert"
if wa_wait_frame "$tmp/inbox" && [ "$rc" = 0 ] && [ "$status" = sent ] && [ "$(wc -l < "$(wa_newest "$tmp/inbox")")" = 2 ] \
   && [ "$(sed -n 1p "$(wa_newest "$tmp/inbox")" | jq -c .)" = "{\"type\":\"auth\",\"token\":\"$token\"}" ] \
   && [ "$(sed -n 2p "$(wa_newest "$tmp/inbox")" | jq -c .)" = "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"$alert\"}}" ] \
   && grep -qP '\tk1\tsent\t' "$log"; then
  pass "alert arrives as the auth line then the user line, and logs sent"
else fail "delivery — rc $rc status $status log $(cat "$log" 2>/dev/null) frame $(cat "$(wa_newest "$tmp/inbox")" 2>/dev/null)"; fi

# 2. JSON-safe: quote, backslash and newline round-trip unchanged.
nasty=$'say "hi" \\ back\nslash and a second line'
deliver "$nasty"
if wa_wait_frame "$tmp/inbox" && [ "$(wc -l < "$(wa_newest "$tmp/inbox")")" = 2 ] \
   && [ "$(sed -n 2p "$(wa_newest "$tmp/inbox")" | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["message"]["content"], end="")')" = "$nasty" ]; then
  pass "an alert with a quote, a backslash and a newline round-trips through json.loads"
else fail "round trip — frame $(cat "$(wa_newest "$tmp/inbox")" 2>/dev/null)"; fi

# 3. No herdr prompt on a delivery.
[ ! -e "$tmp/prompt.called" ] && pass "no herdr prompt call on delivery" || fail "herdr prompt call made: $(cat "$tmp/prompt.called")"

# not_sent <name> <cause substring>: not-sent, the cause named, no frame, rc 1.
not_sent() {
  sleep 0.3
  if [ "$rc" = 1 ] && [ "$status" = not-sent ] && [ "$(wa_frames "$tmp/inbox")" = 0 ] \
     && grep -qP '\tk1\tnot-sent\t' "$log" && grep -qF -- "$2" "$log"; then
    pass "$1 is not-sent naming '$2'"
  else fail "$1 — rc $rc status $status frames $(wa_frames "$tmp/inbox") log: $(cat "$log" 2>/dev/null)"; fi
}

keep="$sessions/$$.json"
mv "$keep" "$tmp/record.bak"
deliver "x"; not_sent "no session record" "no live session record"
mv "$tmp/record.bak" "$keep"

rm -f "$sessions/$$".*.key
deliver "x"; not_sent "no key file" "no key file"

keyfile '{"procStart":"1"}'
deliver "x"; not_sent "a key file without peerToken" "no peerToken"
keyfile 'not json at all'
deliver "x"; not_sent "an unparseable key file" "unreadable key file"
keyfile "{\"peerToken\":\"$token\"}"

record "$tmp/absent.sock"
deliver "x"; not_sent "a socket path that does not exist" "does not exist"

wa_dead_socket "$tmp/dead.sock"
record "$tmp/dead.sock"
deliver "x"; not_sent "a socket nobody listens on" "$tmp/dead.sock"
record "$sock"

# C1: a send killed by a signal prints nothing; the log still names a cause
# and does not blame a missing record.
mkdir -p "$tmp/pybin"; printf '#!/bin/sh\nkill -9 $$\n' > "$tmp/pybin/python3"; chmod +x "$tmp/pybin/python3"
extra_path="$tmp/pybin" deliver "x"
sleep 0.3
if [ "$rc" = 1 ] && grep -qF 'failed with exit 137 and no output' "$log" && ! grep -q 'no live session record' "$log"; then
  pass "a send killed with no output is not-sent naming the exit status, not a missing record"
else fail "silent kill — rc $rc log: $(cat "$log" 2>/dev/null)"; fi

# C2: a key for another process start (a reused pid) is not used; a good key
# beside it is.
other_hex=$(printf 'b%.0s' $(seq 64))
keyfile "{\"peerToken\":\"stale\",\"procStart\":\"1\"}"
deliver "x"; not_sent "only a stale key (another procStart)" "another process start"
printf '{"peerToken":"%s","procStart":"%s"}\n' "$token" "$start" > "$sessions/$$.$other_hex.key"
deliver "x"
if wa_wait_frame "$tmp/inbox" && [ "$status" = sent ] \
   && [ "$(sed -n 1p "$(wa_newest "$tmp/inbox")" | jq -r .token)" = "$token" ]; then
  pass "a stale key beside a good one: the good token is sent"
else fail "stale and good key — status $status log $(cat "$log" 2>/dev/null)"; fi
rm -f "$sessions/$$.$other_hex.key"; keyfile "{\"peerToken\":\"$token\"}"

# The deadline: a second target is not tried when its 5 s no longer fits.
sleep 60 & twin=$!
twin_start=$(stat=$(cat /proc/$twin/stat); set -- ${stat##*) }; echo "${20}")
printf '{"pid":%s,"procStart":"%s","sessionId":"ctl-session","messagingSocketPath":"%s"}\n' "$twin" "$twin_start" "$tmp/absent2.sock" > "$sessions/zz-twin.json"
wa_key "$sessions" "$twin"
record "$tmp/absent.sock"
deadline_s=$((SECONDS - 1)) deliver "x"
kill "$twin" 2>/dev/null; rm -f "$sessions/zz-twin.json" "$sessions/$twin".*.key; record "$sock"
if [ "$rc" = 1 ] && grep -qF 'out of time before trying the next socket' "$log" && ! grep -qF 'absent2.sock' "$log"; then
  pass "twin records: the second socket is not tried once the deadline leaves no room"
else fail "deadline — rc $rc log: $(cat "$log" 2>/dev/null)"; fi

# 4. No herdr prompt call anywhere under flow/claude/hooks (the ticket's rg check).
pat='herdr agent'' prompt'   # split so this file does not match itself
if ! grep -rn "$pat" "$here" | grep -q .; then
  pass "no herdr prompt call remains anywhere under flow/claude/hooks"
else fail "the herdr prompt call is still in $(grep -rln "$pat" "$here")"; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
