#!/usr/bin/env bash
# One home for every shell step the sandcastle-watch skill used to inline in
# prose. Verbs: is-running, start, digest, notify, kill (plus refresh/segment,
# the two entry points folded in from status-refresh.sh and sandcastle-segment.sh).
# SKILL.md carries the judgement — when to watch, what to say — and calls these.
set -uo pipefail

# The live-run pattern, defined ONCE for the whole skill (issue #108). Every
# check that names the orchestrator by command line reuses it, exclusion and all.
LIVE_PAT='tsx \.sandcastle/main\.mts'
TTL=180        # status-file freshness window (segment self-clears past it)
INTERVAL=60    # refresher rewrite cadence, kept well inside TTL

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Naming: bare-named functions (is_running, digest) are reused internally AND
# dispatched; do_* handlers are dispatch-only wrappers; _name are helpers.

# --- process checks ------------------------------------------------------------
# The `grep -v 'bash -c'` self-exclusion lives in exactly ONE place: you invoke
# these from a `bash -c` whose command line carries the very pattern being
# searched, so without it the check finds its own shell. Both the live run and
# the refresher are matched by command line, so both go through _pgrep.
_pgrep() { pgrep -af "$1" | grep -v 'bash -c'; }
# is-running: prints matching lines (pid + cmdline); exit 0 if a run is live, 1 if not.
is_running() { _pgrep "$LIVE_PAT"; }

# --- digest: markers in, status object out (pure over log text) ----------------
# digest <log> <fromOffset>  ->  key=value lines on stdout.
# Reads bytes [fromOffset, EOF) so a tick sees only what is new, and reports the
# markers found there plus the new EOF offset. Buckets a setup-noise failure
# (ExecError exit code with an empty stderr under it) apart from a real one.
digest() {
  local log=$1 from=${2:-0} slice iter flight pr setup allfx fail warn finished
  slice=$(tail -c "+$((from + 1))" "$log")
  iter=$(grep -oE '=== Iteration [0-9]+/[0-9]+' <<<"$slice" | tail -1 | grep -oE '[0-9]+/[0-9]+')
  # ids assigned work since the last iteration header: "  [full] 104: title → …"
  flight=$(awk '/=== Iteration /{buf=""} /^  \[[a-z]+\] [0-9]+:/{buf=buf $2" "} END{print buf}' \
    <(grep -E '=== Iteration |^  \[[a-z]+\] [0-9]+:' <<<"$slice") | tr -cd '0-9 ' | tr -s ' ' | sed 's/^ //;s/ $//')
  pr=$(grep -c '→ PR #' <<<"$slice")
  # setup noise: a ✗ line whose ExecError exit code is followed by a blank line.
  # Git never fails silently, so the blank stderr is the tell the command never ran.
  setup=$(awk '
    /✗ [0-9]+.*ExecError: Command failed \(exit [0-9]+\)/ { id=$2; pend=1; next }
    pend && /^[[:space:]]*$/ { print id; pend=0; next }
    { pend=0 }' <<<"$slice" | tr -cd '0-9\n' | sort -u)
  allfx=$(grep -oE '✗ #?[0-9]+' <<<"$slice" | grep -oE '[0-9]+' | sort -u)
  # a real failure is any ✗ id that the setup-noise bucket did not claim
  fail=$(comm -23 <(printf '%s\n' "$allfx") <(printf '%s\n' "$setup") | tr '\n' ' ' | sed 's/ $//')
  warn=$(grep -oE '⚠ #?[0-9]+' <<<"$slice" | grep -oE '[0-9]+' | sort -u | tr '\n' ' ' | sed 's/ $//')
  finished=0; grep -q '=== Run Summary ===' <<<"$slice" && finished=1
  printf 'iter=%s\n' "${iter:-}"
  printf 'flight=%s\n' "$flight"
  printf 'pr=%s\n' "$pr"
  printf 'fail=%s\n' "$fail"
  printf 'warn=%s\n' "$warn"
  printf 'setup=%s\n' "$(tr '\n' ' ' <<<"$setup" | sed 's/ $//')"
  printf 'offset=%s\n' "$(wc -c <"$log")"
  printf 'done=%s\n' "$finished"
}

# --- notify: the desktop-toast channel (WSL only) ------------------------------
# notify <title> <bodyfile>. The push notification is the harness's job; this is
# the Windows toast that lands on the desktop the user is actually looking at.
# -BodyFile keeps log-derived text out of any shell. Off WSL it is a no-op.
do_notify() {
  command -v powershell.exe >/dev/null || return 0
  powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "$(wslpath -w "$SKILL_DIR/toast.ps1")" -Title "$1" -BodyFile "$(wslpath -w "$2")"
}

# --- start: own the run's whole lifecycle --------------------------------------
# start <log>. setsid puts the npm->tsx->node chain in its own process group so
# one signal reaches all of it; --wait makes this return only when the
# orchestrator truly exits (plain setsid returns at once and fakes completion).
# On exit: one final digest, the run's own summary as the closing report, then
# the temp stdout log is removed (issue #108) — it lived only for the watch.
do_start() {
  local log=$1 status
  setsid --wait npm run sandcastle >"$log" 2>&1
  status=$?
  digest "$log" 0
  sed -n '/=== Run Summary ===/,$p' "$log"
  rm -f "$log"
  return "$status"
}

# --- kill: stop the process GROUP, then prove death by the log going quiet -----
do_kill() {
  local log=$1 pid pgid a b
  pid=$(is_running | awk 'NR==1{print $1}')
  pgid=$(ps -o pgid= -p "${pid:-0}" 2>/dev/null | tr -d ' ')
  [ -z "$pgid" ] && { echo "no run live"; return 0; }
  kill -TERM -"$pgid"; sleep 5
  is_running >/dev/null && kill -KILL -"$pgid"
  a=$(wc -c <"$log"); sleep 20; b=$(wc -c <"$log")
  [ "$a" = "$b" ] && echo "QUIET — dead" || echo "STILL GROWING — alive"
}

# --- refresh + segment: the status-bar file (folded in) ------------------------
DIM=$'\033[2m'; RED=$'\033[31m'; YEL=$'\033[33m'; OFF=$'\033[0m'

_frame() {  # render one status-bar line — digest is the single source of the numbers
  local L=$1 iter='' flight='' pr='' fail='' warn='' k v nfx nwn line
  while IFS='=' read -r k v; do
    case $k in iter) iter=$v;; flight) flight=$v;; pr) pr=$v;; fail) fail=$v;; warn) warn=$v;; esac
  done < <(digest "$L" 0)   # setup-noise ids never reach the bar: digest already split them out
  nfx=$(wc -w <<<"$fail"); nwn=$(wc -w <<<"$warn")
  line="${DIM}🏰 ${iter:-?} · ${flight:-—} · ${pr:-0} PR"
  [ "$nfx" -gt 0 ] && line="$line ${OFF}${RED}· ${nfx}✗ ${fail}${OFF}${DIM}"
  [ "$nwn" -gt 0 ] && line="$line ${OFF}${YEL}· ${nwn}⚠ ${warn}${OFF}${DIM}"
  printf '%s%s\n' "$line" "$OFF"
}

do_refresh() {  # refresh <log> <root> [once]
  local L=$1 F="$2/.sandcastle/logs/watch-status" once=${3:-}
  mkdir -p "$(dirname "$F")"   # gitignored, so a fresh worktree lacks it (issue #108)
  if [ "$once" = once ]; then _frame "$L"; return 0; fi
  while is_running >/dev/null; do _frame "$L" >"$F"; sleep "$INTERVAL"; done
  rm -f "$F"
}

do_segment() {  # segment — the ccstatusline entry, scoped to this session's repo
  local cwd root f
  cwd=$(jq -r '.cwd // .workspace.current_dir // empty' 2>/dev/null)
  [ -n "$cwd" ] || return 0
  root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || root=$cwd
  f="${root:-$cwd}/.sandcastle/logs/watch-status"
  if [ ! -f "$f" ]; then
    [ -d "${root:-$cwd}/.sandcastle" ] && printf '\033[2m🏰 idle\033[0m\n'
    return 0
  fi
  if [ $(( $(date +%s) - $(stat -c %Y "$f") )) -lt "$TTL" ]; then cat "$f"; else printf '\033[2m🏰 idle\033[0m\n'; fi
}

# --- self-check: digest over the captured fixture ------------------------------
_selfcheck() {
  local fx out
  fx="$SKILL_DIR/testdata/run.log"
  out=$(digest "$fx" 0)
  grep -qx 'iter=1/20' <<<"$out" || { echo "FAIL iter: $out"; exit 1; }
  grep -qx 'flight=101 102 104' <<<"$out" || { echo "FAIL flight: $out"; exit 1; }
  grep -qx 'pr=1' <<<"$out" || { echo "FAIL pr: $out"; exit 1; }
  grep -qx 'fail=103' <<<"$out" || { echo "FAIL fail: $out"; exit 1; }
  grep -qx 'warn=104' <<<"$out" || { echo "FAIL warn: $out"; exit 1; }
  grep -qx 'setup=107' <<<"$out" || { echo "FAIL setup: $out"; exit 1; }
  grep -qx 'done=1' <<<"$out" || { echo "FAIL done: $out"; exit 1; }
  echo ok
}

case "${1:-}" in
  is-running)        shift; is_running ;;
  refresher-running) shift; _pgrep 'sandcastle-watch\.sh refresh( |$)' ;;  # boundary: not "refresher-running" (this very check)
  digest)     shift; digest "$@" ;;
  start)      shift; do_start "$@" ;;
  notify)     shift; do_notify "$@" ;;
  kill)       shift; do_kill "$@" ;;
  refresh)    shift; do_refresh "$@" ;;
  segment)    shift; do_segment "$@" ;;
  selfcheck)  shift; _selfcheck ;;
  *) echo "usage: sandcastle-watch.sh {is-running|refresher-running|start|digest|notify|kill|refresh|segment|selfcheck}" >&2; exit 2 ;;
esac
