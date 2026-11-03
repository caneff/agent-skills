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

# Writes to stderr on every call, so a silence assertion has something to catch.
cat > "$tmp/powershell" <<'STUB'
#!/usr/bin/env bash
# Answers what $STUB_DIR/answers/<socket name> holds. `hang` never answers;
# `stubborn` never answers and ignores the TERM a timeout sends.
name=$(basename "$WSL_INTEROP")
echo "$name" >> "$STUB_DIR/calls"
echo "stub stderr noise" >&2
cat >> "$STUB_DIR/stdin-eaten" 2>/dev/null
answer=$(cat "$STUB_DIR/answers/$name" 2>/dev/null) || exit 1
[ "$answer" = hang ] && exec sleep 100
if [ "$answer" = stubborn ]; then trap '' TERM; exec sleep 20; fi
printf '%b' "$answer"
STUB
chmod +x "$tmp/powershell"

fixture() { # fixture <name> <socket>=<answer>... (oldest first) -> sets DIR, SOCKETS, RECORD_DIR
  DIR="$tmp/$1"; SOCKETS="$DIR/run"; RECORD_DIR="$DIR/record"; shift
  mkdir -p "$SOCKETS" "$RECORD_DIR" "$DIR/answers"
  local age=100 pair name
  for pair in "$@"; do
    name="${pair%%=*}_interop"
    python3 -c 'import socket,sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "$SOCKETS/$name"
    touch -d "-$age seconds" "$SOCKETS/$name"
    age=$((age - 10))
    printf '%s' "${pair#*=}" > "$DIR/answers/$name"
  done
}
with_fixture() { # with_fixture <command...>: the environment every start shares
  BASH_ENV="$script" STUB_DIR="$DIR" WSL_INTEROP_POWERSHELL="$tmp/powershell" \
    WSL_INTEROP_SOCKET_DIR="$SOCKETS" WSL_INTEROP_RECORD_DIR="$RECORD_DIR" "$@"
}
# start <WSL_INTEROP> [bash args...]: a new bash reading the script through
# BASH_ENV, printing the WSL_INTEROP it ended up with.
start() {
  local interop=$1; shift
  [ $# -gt 0 ] || set -- -c 'printf %s "$WSL_INTEROP"'
  WSL_INTEROP="$interop" with_fixture bash "$@" </dev/null
}
calls() { cat "$DIR/calls" 2>/dev/null | tr '\n' ' ' | sed 's/_interop//g; s/ $//'; }
record() { cat "$RECORD_DIR/wsl-interop-repoint" 2>/dev/null; }
record_word() { record | cut -d' ' -f2; }
write_record() { printf '%s\n' "$*" > "$RECORD_DIR/wsl-interop-repoint"; }

# --- choosing a socket
fixture newest-wins 10=1 20=0 30='1\r\n'
want "a dead WSL_INTEROP moves to the newest socket reaching a user session" \
  "$SOCKETS/30_interop" "$(start /run/WSL/gone_interop)"

fixture never-zero 10='0\r\n' 20='0\r\n'
want "a live socket reaching session 0 is never chosen" "$DIR/gone" "$(start "$DIR/gone")"
want "every socket answering 0 is recorded as no user session" "no-user-session" "$(record_word)"

fixture skip-zero 10='1\r\n' 20='0\r\n' 30='0\r\n'
want "session 0 sockets are passed over for an older session 1 socket" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture second-session 10='2\r\n'
want "any user session counts, for a sign-in that came after a sign-out" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture garbage 10='' 20='error text\r\n' 30='1 2\r\n' 40='-1\r\n'
want "an empty or unparseable answer is not a session" "$DIR/gone" "$(start "$DIR/gone")"
want "an unparseable answer is recorded as unanswered" "unanswered" "$(record_word)"

fixture failing 20='1\r\n'
rm "$DIR/answers/20_interop"
want "a probe that exits non-zero is not a session" "$DIR/gone" "$(start "$DIR/gone")"
want "a failed probe is recorded as unanswered" "unanswered" "$(record_word)"

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

fixture record-gone 10='1\r\n' 20='1\r\n'
write_record "$EPOCHSECONDS" "$SOCKETS/gone_interop"
want "a remembered socket that no longer exists is probed past" \
  "$SOCKETS/20_interop" "$(start "$DIR/gone")"

fixture record-junk 10='1\r\n'
write_record "junk \$(touch $DIR/ran) text"
want "a malformed record is ignored" "$SOCKETS/10_interop" "$(start "$DIR/gone")"
if [ -e "$DIR/ran" ]; then fail "a record's text was run"; else pass "a record's text is never run"; fi

# Arithmetic evaluates names, so a stamp reaching it unchecked would run this.
fixture stamp-injection 10='1\r\n'
write_record "a[\$(touch\${IFS}$DIR/ran)] no-user-session"
want "a stamp that is no number holds nothing" "$SOCKETS/10_interop" "$(start "$DIR/gone" 2>"$DIR/err")"
if [ -e "$DIR/ran" ]; then fail "a stamp's text was run"; else pass "a stamp's text is never run"; fi

fixture stamp-octal 10='1\r\n'
write_record "08 no-user-session"
want "a stamp with a leading zero is read as decimal" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone" 2>"$DIR/err")"
want "a stamp with a leading zero stays silent" "" "$(cat "$DIR/err")"

fixture stamp-future 10='1\r\n'
write_record "$((EPOCHSECONDS + 1000)) no-user-session"
want "a stamp from the future holds nothing" "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture no-winner 10='0\r\n'
want "no socket reaching a user session leaves the variable as it was" "$DIR/gone" "$(start "$DIR/gone")"
want "that shell probed" "10" "$(calls)"
start "$DIR/gone" >/dev/null
want "the next shell inside a minute does not probe again" "10" "$(calls)"
write_record "$((EPOCHSECONDS - 61)) no-user-session"
start "$DIR/gone" >/dev/null
want "after a minute it probes again" "10 10" "$(calls)"

fixture unanswered-hold 10='0\r\n'
write_record "$((EPOCHSECONDS - 5)) unanswered"
start "$DIR/gone" >/dev/null
want "an unanswered run holds for ten seconds" "" "$(calls)"
write_record "$((EPOCHSECONDS - 11)) unanswered"
start "$DIR/gone" >/dev/null
want "an unanswered run holds no longer than that" "10" "$(calls)"

# --- it never gets in the way
fixture hung 10='1\r\n' 20=hang 30=hang 40=hang 50=hang
started=$EPOCHSECONDS
got=$(start "$DIR/gone"); rc=$?
took=$((EPOCHSECONDS - started))
want "a hung probe still lets the shell start" "0" "$rc"
want "a hung probe leaves the variable as it was once the limit is spent" "$DIR/gone" "$got"
want "running out of time is recorded as unanswered" "unanswered" "$(record_word)"
if [ "$took" -le 4 ]; then pass "hung probes stop inside the 4 s limit (${took}s)"
else fail "hung probes took ${took}s, past the 4 s limit"; fi
if [ "$took" -ge 2 ]; then pass "the limit, not a missing probe, ended that run"
else fail "that run ended in ${took}s, so no probe hung"; fi

fixture hung-then-good 10='1\r\n' 20=hang
want "a hung socket is passed over for a good one" "$SOCKETS/10_interop" "$(start "$DIR/gone")"

fixture stubborn 20=stubborn
started=$EPOCHSECONDS
got=$(start "$DIR/gone")
took=$((EPOCHSECONDS - started))
want "a probe ignoring its timeout leaves the variable as it was" "$DIR/gone" "$got"
if [ "$took" -le 4 ]; then pass "a probe ignoring its timeout is killed inside the 4 s limit (${took}s)"
else fail "a probe ignoring its timeout took ${took}s, past the 4 s limit"; fi

fixture quiet 10='1\r\n'
out=$(start "$DIR/gone" -c 'true' 2>"$DIR/err")
want "a repoint prints nothing on stdout" "" "$out"
want "a repoint prints nothing on stderr" "" "$(cat "$DIR/err")"
want "the stderr check saw a probe that writes to stderr" "10" "$(calls)"

fixture quiet-none 10='0\r\n'
out=$(start "$DIR/gone" -c 'true' 2>"$DIR/err")
want "no winner prints nothing on stdout" "" "$out"
want "no winner prints nothing on stderr" "" "$(cat "$DIR/err")"

fixture no-sockets
out=$(start "$DIR/gone" 2>"$DIR/err")
want "an empty socket directory leaves the variable as it was" "$DIR/gone" "$out"
want "an empty socket directory prints nothing on stderr" "" "$(cat "$DIR/err")"

fixture unwritable 10='1\r\n'
RECORD_DIR="$DIR/no/such/dir"
want "a record that cannot be written does not stop the repoint" \
  "$SOCKETS/10_interop" "$(start "$DIR/gone" 2>"$DIR/err")"
want "a record that cannot be written stays silent" "" "$(cat "$DIR/err")"

# bash carries on after an unbound variable in a BASH_ENV file, so a command
# that ran proves nothing: the file stopping shows as a message and no repoint.
fixture strict-unset 10='1\r\n'
got=$(with_fixture env -u WSL_INTEROP bash -u -c 'printf %s "$WSL_INTEROP"' 2>"$DIR/err" </dev/null)
want "bash -u with WSL_INTEROP unset still repoints" "$SOCKETS/10_interop" "$got"
want "bash -u with WSL_INTEROP unset stays silent" "" "$(cat "$DIR/err")"

fixture strict-record 10='1\r\n'
got=$(with_fixture env -u WSL_INTEROP -u XDG_RUNTIME_DIR bash -u -c 'printf %s "$WSL_INTEROP"' 2>"$DIR/err" </dev/null)
want "bash -u with no runtime dir set still repoints" "$SOCKETS/10_interop" "$got"
want "bash -u with no runtime dir set stays silent" "" "$(cat "$DIR/err")"

fixture status 10='0\r\n'
start "$DIR/gone" -c 'exit 7'; want "the command's exit status comes through" "7" "$?"

fixture stdin 10='1\r\n'
got=$(printf 'input' | WSL_INTEROP="$DIR/gone" with_fixture bash -c 'cat')
want "a probe leaves the command's stdin alone" "input" "$got"
want "the probe did reach the stub" "10" "$(calls)"

# Compared with a bash that never read the script, in case of any new name.
names_after() { # names_after <command starting bash>: names only it holds
  bash -c 'declare -F; compgen -v' | sort -u > "$DIR/plain"
  "$@" -c 'declare -F; compgen -v' | sort -u | comm -13 "$DIR/plain" -
}
fixture clean 10='1\r\n'
want "the script leaves no name behind when it repoints" "" \
  "$(WSL_INTEROP="$DIR/gone" names_after with_fixture bash | grep -vE '^(BASH_ENV|STUB_DIR|WSL_INTEROP_[A-Z_]+)$')"
fixture clean-record 10='1\r\n'
start "$DIR/gone" >/dev/null
want "the script leaves no name behind when it reads the record" "" \
  "$(WSL_INTEROP="$DIR/gone" names_after with_fixture bash | grep -vE '^(BASH_ENV|STUB_DIR|WSL_INTEROP_[A-Z_]+)$')"

# The guard's own job: with no socket directory there is nothing to record.
fixture no-wsl 10='1\r\n'
SOCKETS="$DIR/not-wsl"
want "outside WSL nothing changes" "$DIR/gone" "$(start "$DIR/gone")"
want "outside WSL nothing probes" "" "$(calls)"
want "outside WSL nothing is recorded" "" "$(record)"

exit "$fails"
