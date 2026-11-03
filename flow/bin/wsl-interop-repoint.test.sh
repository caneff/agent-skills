#!/usr/bin/env bash
# Contract test for wsl-interop-repoint.sh (#1625), run the way it runs live: a
# new bash reading it through BASH_ENV. Real socket files in a fixture dir and a
# stub powershell.exe that answers per socket and logs each call, so no Windows
# process starts. The real path is checked live; the PR says how.
# Run: bash flow/bin/wsl-interop-repoint.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/wsl-interop-repoint.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; fails=1; }
want() { # want <name> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 — want [$2], got [$3]"; fi
}

cat > "$tmp/powershell" <<'STUB'
#!/usr/bin/env bash
# Answers what $STUB_DIR/answers/<socket name> holds; `hang` never answers.
name=$(basename "$WSL_INTEROP")
echo "$name" >> "$STUB_DIR/calls"
cat >> "$STUB_DIR/stdin-eaten" 2>/dev/null
answer=$(cat "$STUB_DIR/answers/$name" 2>/dev/null) || exit 1
[ "$answer" = hang ] && exec sleep 100
printf '%b' "$answer"
STUB
chmod +x "$tmp/powershell"

fixture() { # fixture <name> <socket>=<answer>... (oldest first) -> sets DIR, SOCKETS, CACHE
  DIR="$tmp/$1"; SOCKETS="$DIR/run"; CACHE="$DIR/cache"; shift
  mkdir -p "$SOCKETS" "$CACHE" "$DIR/answers"
  local age=100 pair name
  for pair in "$@"; do
    name="${pair%%=*}_interop"
    python3 -c 'import socket,sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "$SOCKETS/$name"
    touch -d "-$age seconds" "$SOCKETS/$name"
    age=$((age - 10))
    printf '%s' "${pair#*=}" > "$DIR/answers/$name"
  done
}
# start <WSL_INTEROP> [bash args...]: a new bash reading the script through
# BASH_ENV, printing the WSL_INTEROP it ended up with.
start() {
  local interop=$1; shift
  [ $# -gt 0 ] || set -- -c 'printf %s "$WSL_INTEROP"'
  WSL_INTEROP="$interop" BASH_ENV="$script" STUB_DIR="$DIR" \
    WSL_INTEROP_POWERSHELL="$tmp/powershell" WSL_INTEROP_SOCKET_DIR="$SOCKETS" \
    WSL_INTEROP_CACHE_DIR="$CACHE" bash "$@" </dev/null
}
calls() { cat "$DIR/calls" 2>/dev/null | tr '\n' ' ' | sed 's/_interop//g; s/ $//'; }

# --- choosing a socket
fixture newest-wins 10=1 20=0 30='1\r\n'
want "a dead WSL_INTEROP moves to the newest socket reaching a user session" \
  "$SOCKETS/30_interop" "$(start /run/WSL/gone_interop)"

fixture never-zero 10='0\r\n' 20='0\r\n'
want "a live socket reaching session 0 is never chosen" "$DIR/gone" "$(start "$DIR/gone")"

fixture skip-zero 10='1\r\n' 20='0\r\n' 30='0\r\n'
want "session 0 sockets are passed over for an older session 1 socket" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture second-session 10='2\r\n'
want "any user session counts, for a sign-in that came after a sign-out" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture garbage 10='' 20='error text\r\n' 30='1 2\r\n' 40='-1\r\n'
want "an empty or unparseable answer is not a session" "$DIR/gone" "$(start "$DIR/gone")"

fixture failing 20='1\r\n'
rm "$DIR/answers/20_interop"
want "a probe that exits non-zero is not a session" "$DIR/gone" "$(start "$DIR/gone")"

fixture unset-var 10='1\r\n'
want "an unset WSL_INTEROP is repointed like a dead one, since it reaches session 0" \
  "$SOCKETS/10_interop" "$(start "")"

# --- the cost of each path
fixture live 10='0\r\n' 20='1\r\n'
want "a live WSL_INTEROP stays put" "$SOCKETS/10_interop" "$(start "$SOCKETS/10_interop")"
want "a live WSL_INTEROP runs no Windows process" "" "$(calls)"

fixture repeat 10='1\r\n'
want "the first shell in a dead tree probes" "$SOCKETS/10_interop" "$(start "$DIR/gone")"
want "the first shell probed once" "10" "$(calls)"
want "the next shell in that tree gets the same socket" "$SOCKETS/10_interop" "$(start "$DIR/gone")"
want "the next shell runs no Windows process" "10" "$(calls)"

fixture cache-gone 10='1\r\n' 20='1\r\n'
printf '%s %s\n' "$EPOCHSECONDS" "$SOCKETS/gone_interop" > "$CACHE/wsl-interop-repoint"
want "a remembered socket that no longer exists is probed past" \
  "$SOCKETS/20_interop" "$(start "$DIR/gone")"

fixture cache-junk 10='1\r\n'
printf 'junk $(touch %s/ran) text\n' "$DIR" > "$CACHE/wsl-interop-repoint"
want "a malformed record is ignored" "$SOCKETS/10_interop" "$(start "$DIR/gone")"
if [ -e "$DIR/ran" ]; then fail "a record's text was run"; else pass "a record's text is never run"; fi

fixture no-winner 10='0\r\n'
want "no socket reaching a user session leaves the variable as it was" "$DIR/gone" "$(start "$DIR/gone")"
want "that shell probed" "10" "$(calls)"
start "$DIR/gone" >/dev/null
want "the next shell inside a minute does not probe again" "10" "$(calls)"
printf '%s \n' "$((EPOCHSECONDS - 61))" > "$CACHE/wsl-interop-repoint"
start "$DIR/gone" >/dev/null
want "after a minute it probes again" "10 10" "$(calls)"

# --- it never gets in the way
fixture hung 10='1\r\n' 20=hang 30=hang 40=hang 50=hang
started=$EPOCHSECONDS
got=$(start "$DIR/gone"); rc=$?
took=$((EPOCHSECONDS - started))
want "a hung probe still lets the shell start" "0" "$rc"
want "a hung probe leaves the variable as it was once the limit is spent" "$DIR/gone" "$got"
if [ "$took" -le 9 ]; then pass "hung probes stop inside the 9 s limit (${took}s)"
else fail "hung probes took ${took}s, past the 9 s limit"; fi
if [ "$took" -ge 3 ]; then pass "the limit, not a missing probe, ended that run"
else fail "that run ended in ${took}s, so no probe hung"; fi

fixture hung-then-good 10='1\r\n' 20=hang
want "a hung socket is passed over for a good one" "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture quiet 10='1\r\n'
out=$(start "$DIR/gone" -c 'true' 2>"$DIR/err")
want "a repoint prints nothing on stdout" "" "$out"
want "a repoint prints nothing on stderr" "" "$(cat "$DIR/err")"

fixture quiet-none 10='0\r\n'
out=$(start "$DIR/gone" -c 'true' 2>"$DIR/err")
want "no winner prints nothing on stdout" "" "$out"
want "no winner prints nothing on stderr" "" "$(cat "$DIR/err")"

fixture unwritable 10='1\r\n'
CACHE="$DIR/no/such/dir"
want "a record that cannot be written does not stop the repoint" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone" 2>"$DIR/err")"
want "a record that cannot be written stays silent" "" "$(cat "$DIR/err")"

fixture strict 10='0\r\n'
want "bash -eu survives every path and runs the command" "ran" \
  "$(start "$DIR/gone" -eu -c 'echo ran')"
want "bash -eu survives an unset WSL_INTEROP" "ran" \
  "$(BASH_ENV="$script" STUB_DIR="$DIR" WSL_INTEROP_POWERSHELL="$tmp/powershell" \
     WSL_INTEROP_SOCKET_DIR="$SOCKETS" WSL_INTEROP_CACHE_DIR="$CACHE" \
     env -u WSL_INTEROP bash -eu -c 'echo ran')"

fixture status 10='0\r\n'
start "$DIR/gone" -c 'exit 7'; want "the command's exit status comes through" "7" "$?"

fixture stdin 10='1\r\n'
got=$(printf 'input' | WSL_INTEROP="$DIR/gone" BASH_ENV="$script" STUB_DIR="$DIR" \
  WSL_INTEROP_POWERSHELL="$tmp/powershell" WSL_INTEROP_SOCKET_DIR="$SOCKETS" \
  WSL_INTEROP_CACHE_DIR="$CACHE" bash -c 'cat')
want "a probe leaves the command's stdin alone" "input" "$got"
want "the probe did reach the stub" "10" "$(calls)"

fixture clean 10='1\r\n'
want "the script leaves no function behind" "" "$(start "$DIR/gone" -c 'declare -F')"
want "the script leaves no variable behind" "" \
  "$(start "$DIR/gone" -c 'compgen -v | grep -E "^(_+wsl|interop_)" || true')"

fixture no-wsl 10='1\r\n'
SOCKETS="$DIR/not-wsl"
want "outside WSL nothing changes" "$DIR/gone" "$(start "$DIR/gone")"
want "outside WSL nothing probes" "" "$(calls)"

exit "$fails"
