#!/usr/bin/env bash
# One home for every shell step the sandcastle-watch skill used to inline in
# prose. Verbs: is-running, start, digest, notify, kill (plus refresh/segment,
# the two entry points folded in from status-refresh.sh and sandcastle-segment.sh).
# SKILL.md carries the judgement — when to watch, what to say — and calls these.
set -uo pipefail

# The live-run pattern, defined ONCE for the whole skill. Every
# check that names the orchestrator by command line reuses it, exclusion and all.
LIVE_PAT='tsx \.sandcastle/main\.mts'
TTL=180        # status-file freshness window (segment self-clears past it)
INTERVAL=60    # refresher rewrite cadence, kept well inside TTL

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Naming: bare-named functions (is_running, digest) are reused internally AND
# dispatched; do_* handlers are dispatch-only wrappers; _name are helpers.

# The `grep -v 'bash -c'` self-exclusion lives in exactly ONE place: you invoke
# these from a `bash -c` whose command line carries the very pattern being
# searched, so without it the check finds its own shell. Both the live run and
# the refresher are matched by command line, so both go through _pgrep.
_pgrep() { pgrep -af "$1" | grep -v 'bash -c'; }
# is-running: prints matching lines (pid + cmdline); exit 0 if a run is live, 1 if not.
is_running() { _pgrep "$LIVE_PAT"; }

# digest <log> <fromOffset>  ->  key=value lines on stdout.
# Reads bytes [fromOffset, EOF) so a tick sees only what is new, and reports the
# SANDCASTLE_MARK sentinels found there plus the new EOF offset. setup noise and
# real failures arrive already split — the emitter classified them at the source.
# The deduped ids from every `SANDCASTLE_MARK <kind> <id>` line in the slice,
# space-joined. One id per marker (fail/warn/setup), so $3 is it.
_mark_ids() { grep -E "^SANDCASTLE_MARK $1 " <<<"$2" | awk '{print $3}' | sort -u | tr '\n' ' ' | sed 's/ $//'; }

digest() {
  local log=$1 from=${2:-0} slice plan flight pr fail warn setup finished
  slice=$(tail -c "+$((from + 1))" "$log")
  # Every field comes from a SANDCASTLE_MARK sentinel the orchestrator prints
  # (markers.mts). Human wording is never parsed. The emitter already split setup
  # noise from real failure, so there is no stderr-shape heuristic here.
  # $3 is the first arg after "SANDCASTLE_MARK <kind>": the id (or the count).
  plan=$(grep -E '^SANDCASTLE_MARK plan ' <<<"$slice" | tail -1 | awk '{print $3}')
  flight=$(grep -E '^SANDCASTLE_MARK flight ' <<<"$slice" | tail -1 | sed -E 's/^SANDCASTLE_MARK flight //')
  pr=$(grep -cE '^SANDCASTLE_MARK pr ' <<<"$slice")
  fail=$(_mark_ids fail "$slice")
  warn=$(_mark_ids warn "$slice")
  setup=$(_mark_ids setup "$slice")
  finished=0; grep -q '^SANDCASTLE_MARK done' <<<"$slice" && finished=1
  printf 'plan=%s\n' "${plan:-}"
  printf 'flight=%s\n' "$flight"
  printf 'pr=%s\n' "$pr"
  printf 'fail=%s\n' "$fail"
  printf 'warn=%s\n' "$warn"
  printf 'setup=%s\n' "$setup"
  printf 'offset=%s\n' "$(wc -c <"$log")"
  printf 'done=%s\n' "$finished"
}

# notify <title> <bodyfile>. The push notification is the harness's job; this is
# the Windows toast that lands on the desktop the user is actually looking at.
# -BodyFile keeps log-derived text out of any shell. Off WSL it is a no-op.
do_notify() {
  command -v powershell.exe >/dev/null || return 0
  powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "$(wslpath -w "$SKILL_DIR/toast.ps1")" -Title "$1" -BodyFile "$(wslpath -w "$2")"
}

# start <log>. setsid puts the npm->tsx->node chain in its own process group so
# one signal reaches all of it; --wait makes this return only when the
# orchestrator truly exits (plain setsid returns at once and fakes completion).
# On exit: one final digest, the run's own summary as the closing report, then
# the temp stdout log is removed — it lived only for the watch.
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

DIM=$'\033[2m'; RED=$'\033[31m'; YEL=$'\033[33m'; OFF=$'\033[0m'

_frame() {  # render one status-bar line — digest is the single source of the numbers
  local L=$1 plan='' flight='' pr='' fail='' warn='' k v nfx nwn line
  while IFS='=' read -r k v; do
    case $k in plan) plan=$v;; flight) flight=$v;; pr) pr=$v;; fail) fail=$v;; warn) warn=$v;; esac
  done < <(digest "$L" 0)   # setup-noise ids never reach the bar: digest already split them out
  nfx=$(wc -w <<<"$fail"); nwn=$(wc -w <<<"$warn")
  line="${DIM}🏰 ${plan:-?} · ${flight:-—} · ${pr:-0} PR"
  [ "$nfx" -gt 0 ] && line="$line ${OFF}${RED}· ${nfx}✗ ${fail}${OFF}${DIM}"
  [ "$nwn" -gt 0 ] && line="$line ${OFF}${YEL}· ${nwn}⚠ ${warn}${OFF}${DIM}"
  printf '%s%s\n' "$line" "$OFF"
}

do_refresh() {  # refresh <log> <root> [once]
  local L=$1 F="$2/.sandcastle/logs/watch-status" once=${3:-}
  mkdir -p "$(dirname "$F")"   # gitignored, so a fresh worktree lacks it
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

_selfcheck() {
  local fx out
  fx="$SKILL_DIR/testdata/run.log"
  out=$(digest "$fx" 0)
  grep -qx 'plan=4' <<<"$out" || { echo "FAIL plan: $out"; exit 1; }
  grep -qx 'flight=101 102 104 107' <<<"$out" || { echo "FAIL flight: $out"; exit 1; }
  grep -qx 'pr=1' <<<"$out" || { echo "FAIL pr: $out"; exit 1; }
  grep -qx 'fail=102' <<<"$out" || { echo "FAIL fail: $out"; exit 1; }
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
