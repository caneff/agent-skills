#!/usr/bin/env bash
# Single-diff witness mode (#1331): does one covering test notice one change?
#
#   witness.sh --patch <file> --test '<covering test command>'
#              [--worktree <path>] [--id <id>] [--call-site]
#              (--repo <repo> --ticket <n> [--round <k>] [--ledger <path>] | --no-ledger)
#
# Applies the patch in a throwaway worktree of --worktree's HEAD (default: the
# current directory's repo) and runs the command there, through
# multi-axis-code-review/witness-check.sh, which owns the worktree, the Python
# bytecode and node_modules setup, the `unknown` rules and the ledger row.
# Prints that script's report, then one last line: `outcome: red`, `green` or
# `unknown`. red carries the suite's own message above it; green means the
# test passed with the patch applied (a hollow witness); unknown means the
# patch did not apply or the command never ran.
#
# Exit: 0 when an outcome line was printed; otherwise witness-check.sh's own
# non-zero exit (its header lists them), or 1 when its report carried no
# outcome for the id.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() { sed -n '/^#   witness.sh/,/^#$/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# //' >&2; exit 2; }

patch="" test_cmd="" worktree="." id="diff" call_site=0 pass=()
while [ $# -gt 0 ]; do
  case "$1" in
    --patch) [ $# -ge 2 ] || usage; patch="$2"; shift 2 ;;
    --test) [ $# -ge 2 ] || usage; test_cmd="$2"; shift 2 ;;
    --worktree) [ $# -ge 2 ] || usage; worktree="$2"; shift 2 ;;
    --id) [ $# -ge 2 ] || usage; id="$2"; shift 2 ;;
    --call-site) call_site=1; shift ;;
    --repo|--ticket|--round|--ledger) [ $# -ge 2 ] || usage; pass+=( "$1" "$2" ); shift 2 ;;
    --no-ledger) pass+=( "$1" ); shift ;;
    *) echo "single-diff witness: unknown argument '$1'" >&2; usage ;;
  esac
done
[ -n "$patch" ] && [ -n "$test_cmd" ] || usage
[ -f "$patch" ] && [ -r "$patch" ] || { echo "single-diff witness: cannot read patch '$patch'" >&2; exit 2; }
[ "$call_site" -eq 1 ] && pass+=( --call-site "$id" )

WITNESS_PATCH="$(realpath "$patch")"
WITNESS_TEST="$test_cmd"
export WITNESS_PATCH WITNESS_TEST

report="$(bash "$here/../multi-axis-code-review/witness-check.sh" \
  --worktree "$worktree" --mutate "$here/witness-mutate.sh" "${pass[@]}" -- "$id")"
status=$?
[ -n "$report" ] && printf '%s\n' "$report"
[ "$status" -eq 0 ] || exit "$status"
# The report's line for the id is the outcome; its absence is never a pass.
case "$(printf '%s\n' "$report" | sed -n "s/^$id: \([A-Za-z]*\) .*/\1/p" | head -1)" in
  red) echo "outcome: red" ;;
  HOLLOW) echo "outcome: green" ;;
  unknown) echo "outcome: unknown" ;;
  *) echo "single-diff witness: the witness check reported no outcome for '$id'" >&2; exit 1 ;;
esac
