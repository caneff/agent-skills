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
# hook (`stop_hook_active`) passes. Not a worker, no transcript, or no jq: pass.
set -u
hook_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
gate="$hook_dir/../../../implement/pre-report-gate.sh"

event="$(cat)"
jq -e '.stop_hook_active != true' >/dev/null 2>&1 <<<"$event" || exit 0
transcript="$(jq -r '.transcript_path // ""' <<<"$event" 2>/dev/null)"
cwd="$(jq -r '.cwd // ""' <<<"$event" 2>/dev/null)"
[ -r "$transcript" ] || exit 0

# shellcheck source=worker-alert-lib.sh
source "$hook_dir/worker-alert-lib.sh" 2>/dev/null || exit 0
declare -F worker_alert_read_brief >/dev/null || exit 0
brief="$(worker_alert_read_brief "$transcript")"
[ -n "$brief" ] || exit 0

block() { jq -nc --arg r "$1" '{decision:"block", reason:$r}'; exit 0; }
[ -x "$gate" ] || [ -r "$gate" ] || block "worker-dirty-stop: cannot find $gate, so the tree could not be checked; commit or remove uncommitted work, then stop"
[ -d "$cwd" ] || block "worker-dirty-stop: the session cwd '$cwd' is not a directory, so the tree could not be checked"

out="$(cd "$cwd" && PRE_REPORT_TREE_ONLY=1 bash "$gate" HEAD 2>&1)"
rc=$?
[ "$rc" -eq 0 ] && exit 0
block "You are stopping with uncommitted work (a worker's report must describe the branch, not the tree). Commit it or remove it, then report. ${out}"
