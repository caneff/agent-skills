#!/usr/bin/env bash
# Stop hook (#1907): a worker may not stop with uncommitted work in its tree.
#
# Contract: read the Stop event JSON on stdin. The session is a worker when
# its transcript opens with an `/implement` or `/implement-spec` brief
# carrying `--controller "<name>"` (the same reader worker-stop-alert.sh
# uses). For a worker, run the pre-report gate's clean-tree check
# (`PRE_REPORT_TREE_ONLY=1 implement/pre-report-gate.sh HEAD`) in the event's
# cwd. Dirty — or a cwd the check cannot judge — prints
# {"decision":"block","reason":...} so the worker keeps going and commits or
# removes the files. Only the tree check runs: a stop for a question has no
# sha, scratch or dispositions to judge yet, and the full gate stays the
# worker's step before "PR up".
# A second consecutive block would loop, so a stop already continued by a
# hook (`stop_hook_active`) passes; if the tree is still dirty then, that is
# logged. Not a worker or no transcript: pass. A lib or jq that is missing
# also passes, but is logged to ~/.claude/worker-dirty-stop.log, never
# silent. The log is the only record of a pass over a dirty tree.
set -u
hook_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
gate="$hook_dir/../../../implement/pre-report-gate.sh"

log="$HOME/.claude/worker-dirty-stop.log"
note() { mkdir -p "$(dirname "$log")"; printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$log"; }
block() { jq -nc --arg r "$1" '{decision:"block", reason:$r}'; exit 0; }

command -v jq >/dev/null 2>&1 || { note "jq-missing" "every worker stop passes unchecked"; exit 0; }
event="$(cat)"
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
cwd="$(jq -r '.cwd // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

# shellcheck source=worker-alert-lib.sh
source "$hook_dir/worker-alert-lib.sh" 2>/dev/null && declare -F worker_alert_read_brief >/dev/null || {
  note "lib-missing" "$hook_dir/worker-alert-lib.sh unreadable or lacks worker_alert_read_brief; every worker stop passes unchecked"
  exit 0
}
brief="$(worker_alert_read_brief "$transcript")"
[ -n "$brief" ] || exit 0

active=false
jq -e '.stop_hook_active == true' >/dev/null 2>&1 <<<"$event" && active=true

[ -r "$gate" ] || { [ "$active" = true ] || block "worker-dirty-stop: cannot find $gate, so the tree could not be checked; commit your work and report"; exit 0; }
[ -d "$cwd" ] || { [ "$active" = true ] || block "worker-dirty-stop: the session cwd '$cwd' is not a directory, so the tree could not be checked"; exit 0; }

out="$(cd "$cwd" && PRE_REPORT_TREE_ONLY=1 bash "$gate" HEAD 2>&1)"
rc=$?
[ "$rc" -eq 0 ] && exit 0
if [ "$active" = true ]; then
  note "passed-dirty" "$cwd: stop already continued once; ${out%%$'\n'*}"
  exit 0
fi
case "$rc" in
  1) block "You are stopping with uncommitted work. Commit it (a WIP commit is fine); delete only what you created and no longer need, and ask before deleting anything else. If you already sent your report, send a corrected one naming the new sha. ${out}" ;;
  *) block "worker-dirty-stop: the tree check could not run (pre-report gate exit $rc), so the tree was not judged clean: ${out}" ;;
esac
