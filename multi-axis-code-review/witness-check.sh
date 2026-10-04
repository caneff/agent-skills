#!/usr/bin/env bash
# The witness check (SKILL.md § 4, *What the witness check costs*): one
# throwaway git worktree per mutation, the mutations run concurrently under the
# box bound, each one's message printed under its own id, and an unreached
# mutation reported as `unknown`, never as a pass.
#
#   witness-check.sh --worktree <reviewed tree> --mutate <file>
#                    (--repo <repo> --ticket <n> [--round <k>] [--ledger <path>] | --no-ledger)
#                    [--call-site <id>]... -- <id>...
#
# <file> is sourced and must define `mutate`: $1 the id, $2 the witness
# worktree, $3 a marker path. It strips that test's constraint in $2, creates
# the marker with `: >"$3"` on the line IMMEDIATELY before the covering suite's
# command, and runs only that suite. A `--call-site` id is one of the ids, and
# its ledger row is typed call-site-mutation instead of witness-mutation.
#
# Before `mutate` runs, every witness gets the setup a fresh worktree lacks
# (#1219): PYTHONDONTWRITEBYTECODE=1 and no `__pycache__` (why: at the export
# below), and, when the reviewed tree's top level has a `node_modules` and the
# witness has none, a symlink to it, so a Node suite fails on the mutation, not
# a missing module. The link is shared with the reviewed tree, not a copy: a
# workspace package that `node_modules` links back into the tree resolves to
# the reviewed tree's files, a tool cache written through it lands there, and
# the link shows as untracked where `.gitignore` says `node_modules/`
# (docs/research/2026-10-04-witness-node-modules-symlink.md).
#
# Exit: 0 every mutation was run and reported (red, HOLLOW or unknown — read
# the output); 1 setup failed before any mutation; 2 bad arguments; 3 a
# throwaway worktree could not be removed and is still registered; 4 a ledger
# row was refused; 130 interrupted.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() { sed -n '/^#   witness-check.sh/,/^#$/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# //' >&2; exit 2; }
worktree="" mutate_file="" no_ledger=0 repo_name=""
ledger_args=() call_site_ids=" "
while [ $# -gt 0 ]; do
  case "$1" in
    --worktree) worktree="${2-}"; shift 2 || usage ;;
    --mutate) mutate_file="${2-}"; shift 2 || usage ;;
    --repo|--ticket|--round|--ledger) [ $# -ge 2 ] || usage; ledger_args+=( "$1" "$2" )
      [ "$1" = --repo ] && repo_name="$2"; shift 2 ;;
    --no-ledger) no_ledger=1; shift ;;
    --call-site) [ $# -ge 2 ] || usage; call_site_ids="$call_site_ids$2 "; shift 2 ;;
    --) shift; break ;;
    *) echo "witness check: unknown argument '$1'" >&2; usage ;;
  esac
done
mutations=( "$@" )
[ -n "$worktree" ] && [ -n "$mutate_file" ] || usage
# Ledger rows are the review's cost record (#1270): a run that forgot its
# --repo/--ticket would otherwise drop them silently, so skipping them is said.
if [ "$no_ledger" -eq 1 ]; then
  [ "${#ledger_args[@]}" -eq 0 ] || { echo "witness check: --no-ledger with ledger arguments" >&2; exit 2; }
else
  case " ${ledger_args[*]-} " in *" --repo "*" --ticket "*|*" --ticket "*" --repo "*) ;;
    *) echo "witness check: ledger rows need --repo and --ticket (or --no-ledger)" >&2; exit 2 ;;
  esac
fi
[ -r "$mutate_file" ] || { echo "witness check: cannot read mutate file '$mutate_file'" >&2; exit 2; }
# shellcheck source=/dev/null
. "$mutate_file" || { echo "witness check: sourcing '$mutate_file' failed" >&2; exit 2; }
declare -F mutate >/dev/null || { echo "witness check: '$mutate_file' does not define mutate" >&2; exit 2; }

# Job control, so each background mutation is its own process group and an
# interrupt can reach a covering suite's whole process tree rather than only
# the wrapper shell around it. An interrupted run may print a job notice.
set -m
top=$(git -C "$worktree" rev-parse --show-toplevel) || exit 1
# An empty list is a failed enumeration upstream, not a clean check: every loop
# below would run zero times, cleanup would succeed, and the run would report
# success having witnessed nothing. Refused before anything is created.
if [ "${#mutations[@]}" -eq 0 ]; then
  echo "witness check: no mutations supplied - nothing was checked" >&2; exit 2
fi
# An id names a directory and an output file, so it is checked before anything
# exists: a pytest nodeid (`tests/a.py::t1[x]`) would put a mutation's output
# file inside its own worktree and break the per-id prefixing below. Refused by
# name — map the test to a short id and report the mapping — never mangled.
# A `*` reaches here only when the caller's shell left it unexpanded, and is
# refused the same way.
seen=" "
for id in "${mutations[@]}"; do
  case "$id" in ''|*[!A-Za-z0-9._-]*)
    echo "witness check: '$id' is not usable as a mutation id (letters, digits, . - _)" >&2; exit 2;;
  esac
  case "$seen" in *" $id "*)
    echo "witness check: id '$id' is named twice - one mutation would overwrite the other's output" >&2; exit 2;;
  esac
  seen="$seen$id "
done
for id in $call_site_ids; do
  case "$seen" in *" $id "*) ;;
    *) echo "witness check: call-site id '$id' is not among the mutation ids - it would never run" >&2; exit 2;;
  esac
done
# One home (#1324): the review cache's `<repo>` directory, where every other
# file of a review lives and the 14-day sweep reaches, rather than a /tmp
# directory nothing names. `--no-ledger` runs have no repo and keep `mktemp -d`.
if [ -n "$repo_name" ]; then
  home_dir="${HOME:?}/.cache/agent-reviews/$repo_name"
  mkdir -p "$home_dir" && root=$(mktemp -d "$home_dir/witness.XXXXXX") || exit 1
else
  root=$(mktemp -d) || exit 1
fi
# Checked, not assumed: a TMPDIR (or HOME) under the reviewed tree would put the
# throwaway worktrees inside the checkout, and those untracked directories then
# block `git worktree remove` and `ship` long after the review reported green.
case "$root" in "$top"/*)
  rmdir "$root"
  echo "witness check: the worktree root is inside the checkout ($root)" >&2; exit 1;;
esac
# Worktrees, outputs and statuses get disjoint directories: with all three in
# one, the ids `x` and `x.out` are both legal and collide - the parent creates
# worktree `x.out` while mutation `x` is opening its output file at that same
# path, so `x`'s redirection fails against a directory and `x` is reported red
# without its suite ever having run.
mkdir -p "$root/worktrees" "$root/output" "$root/status" "$root/ran" "$root/seconds" "$root/outcome" || exit 1
# Cleanup that reports rather than covers: an `rm -rf` over a worktree git
# failed to deregister - a full disk is the plausible way - leaves exactly the
# stale entry SKILL.md says never to create, and the run would exit 0 having
# created it. A failed removal keeps its directory, keeps the root, and says so.
cleanup() {
  cleanup_failed=0
  for w in "$root"/worktrees/*/; do
    [ -d "$w" ] || continue
    git -C "$worktree" worktree remove --force "${w%/}" && continue
    cleanup_failed=$(( cleanup_failed + 1 ))
    echo "witness check: could not remove worktree ${w%/} - it is still registered" >&2
  done
  if [ "$cleanup_failed" -gt 0 ]; then
    echo "witness check: $cleanup_failed worktree(s) left registered; keeping $root - list them with git worktree list and remove them by hand" >&2
    return 1
  fi
  rm -rf "$root" 2>/dev/null
}
# Armed before the first `worktree add` and sweeping every mutation, because a
# witness check that WORKS makes the covering suite fail — that failure is the
# whole point, and it is the ordinary outcome, not the exceptional one. INT and
# TERM as well: this run is minutes long, so a reviewer's ctrl-C is an ordinary
# way for it to end, and it would otherwise leave N registered worktrees behind
# to stall the next `worktree remove` and any later `merge-cleanup`.
# Signalling this shell does not reach its background children, so without this
# the covering suites keep running after their worktrees are force-removed,
# holding the box and writing into deleted paths. Stop them, reap them, and only
# then clean up.
stop_children() {
  pids=$(jobs -pr)
  [ -n "$pids" ] || return 0
  for pid in $pids; do kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; done
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -n "$(jobs -pr)" ] || break
    sleep 0.5
  done
  for pid in $(jobs -pr); do kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null; done
  wait 2>/dev/null
}
trap cleanup EXIT
trap 'stop_children; cleanup; exit 130' INT TERM
# The bound and its reason are SKILL.md's *The bound*. What the code adds is the
# refusal to guess: no readable process table means a full box, not an idle one.
if procs=$(ps -eo comm= 2>/dev/null) && [ -n "$procs" ]; then
  busy=$(printf '%s\n' "$procs" | { grep -cx claude || true; })
else
  busy=28
fi
slots=$(( (28 - busy) / 3 )); [ "$slots" -gt 4 ] && slots=4; [ "$slots" -lt 1 ] && slots=1
# A mutation's own output, head AND tail, every line tagged with the id that
# produced it: pytest puts the assertion text at the end, so the head alone cuts
# out exactly what you are reading for.
show() {
  n=$(wc -l <"$root/output/$1" 2>/dev/null || echo 0)
  if [ "$n" -le 50 ]; then cat "$root/output/$1"
  else head -25 "$root/output/$1"
       printf '... %s lines omitted from the middle ...\n' "$(( n - 50 ))"
       tail -25 "$root/output/$1"
  fi 2>/dev/null | awk -v p="  $1| " '{print p $0}'
}
# Never write bytecode in a witness. Python trusts a .pyc whose recorded source
# mtime (to the second) and size match, so a body that runs its suite, makes a
# same-size edit and runs it again inside one second reads the first run's
# bytecode and reports HOLLOW for a test that would have gone red.
export PYTHONDONTWRITEBYTECODE=1
# The witness setup a fresh worktree lacks. Any failure leaves the mutation
# unreached, so it is reported `unknown` by the marker check below.
prepare() { # <witness>
  find "$1" -name __pycache__ -type d -prune -exec rm -rf {} + || {
    echo "witness check: could not clear __pycache__ in $1" >&2; return 1; }
  if [ -d "$top/node_modules" ] && [ ! -e "$1/node_modules" ] && [ ! -L "$1/node_modules" ]; then
    ln -s "$top/node_modules" "$1/node_modules" || {
      echo "witness check: could not link node_modules into $1" >&2; return 1; }
  fi
}
for id in "${mutations[@]}"; do
  while [ "$(jobs -pr | wc -l)" -ge "$slots" ]; do wait -n; done
  witness="$root/worktrees/$id"
  started=$(date +%s)
  if ! git -C "$worktree" worktree add --detach -q "$witness" HEAD || ! prepare "$witness"; then
    printf 'unknown\n' >"$root/status/$id"   # class 1: an unreached mutation is not a pass
    printf '%s\n' "$(( $(date +%s) - started ))" >"$root/seconds/$id"   # the time the failed attempt took, never a stand-in zero
    continue
  fi
  # `mutate` in its own subshell: a mutation body ends in a failing suite and
  # is naturally written with `exit`, which would otherwise kill this job
  # before its status is recorded and read back below as `unknown`.
  { ( mutate "$id" "$witness" "$root/ran/$id" ) >"$root/output/$id" 2>&1
    printf '%s\n' "$?" >"$root/status/$id"
    printf '%s\n' "$(( $(date +%s) - started ))" >"$root/seconds/$id"; } &
done
wait
for id in "${mutations[@]}"; do
  # The marker says the wrapper reached the line before the covering suite - a
  # wrapper that dies earlier (a missing test path, a denied command) exits
  # nonzero and writes an error, and without this that reads as an assertion
  # witnessed.
  if [ ! -e "$root/ran/$id" ]; then
    printf '%s: unknown — it never reached its covering suite, whatever it exited with\n' "$id"
    show "$id"   # what it said on the way: a patch that did not apply, a missing path
    printf 'unknown\n' >"$root/outcome/$id"
    continue
  fi
  # 126 and 127 are the kernel answering directly: the command was not
  # executable, or was not found, so it never started. The marker cannot know
  # that - it is written on the line before - and every proxy for "the suite
  # ran" is a proxy. Where a real answer exists, take it instead of inferring.
  case "$(cat "$root/status/$id" 2>/dev/null)" in
    126|127) printf '%s: unknown — its covering suite command never executed (not found, or not executable)\n' "$id"
             show "$id"
             printf 'unknown\n' >"$root/outcome/$id" ;;
    0) printf '%s: HOLLOW — the assertion still passed with its constraint stripped\n' "$id"
       printf 'green\n' >"$root/outcome/$id" ;;
    [1-9]*) printf '%s: red — its own message follows; confirm it is your assertion, not a missing file or a denied path\n' "$id"
            show "$id"
            printf 'red\n' >"$root/outcome/$id" ;;
    *) printf '%s: unknown — the mutation never ran to completion; report it by name, never as a pass\n' "$id"
       printf 'unknown\n' >"$root/outcome/$id" ;;
  esac
done
# One ledger row per mutation (#1270), written here because cleanup removes the files.
# The outcome is the word the report loop above wrote for the id (`red`, `green` or
# `unknown`), so the mapping from exit status to outcome has this one home; a missing
# outcome file or wall clock is refused by `append`, never written as a stand-in.
append_failed=0
if [ "$no_ledger" -eq 0 ]; then
  for id in "${mutations[@]}"; do
    kind=witness-mutation
    case "$call_site_ids" in *" $id "*) kind=call-site-mutation ;; esac
    python3 "$here/../docs/research/review_ledger.py" append "${ledger_args[@]}" --type "$kind" \
      --mutation-id "$id" --status-file "$root/outcome/$id" --seconds "$(cat "$root/seconds/$id" 2>/dev/null)" \
      || append_failed=$(( append_failed + 1 ))
  done
fi
cleanup || exit 3
trap - EXIT INT TERM
[ "$append_failed" -eq 0 ] || { echo "witness check: $append_failed mutation row(s) not appended - put the refusal above on the first line of your summary" >&2; exit 4; }
exit 0
