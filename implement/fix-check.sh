#!/usr/bin/env bash
# The merge check (#1401): every review finding of ticket <n> has one
# disposition, a `fixed` sha is a commit on the PR branch, a `moved` ticket is
# open, and an empty findings sidecar carries its completion marker. The rules
# and exit codes are in fix_check.py's docstring. Used by pre-report-gate.sh
# (worker) and by § The merge step 2 (controller).
# Usage: bash fix-check.sh <n> [<branch, default implement-<n>>]
exec python3 "$(dirname "${BASH_SOURCE[0]}")/fix_check.py" "$@"
