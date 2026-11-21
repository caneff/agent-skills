#!/usr/bin/env bash
# The witness check (SKILL.md § 4, *What the witness check costs*): ONE mutation per call,
# given by flags, applied as one literal string replacement in its own throwaway git worktree,
# its covering command run there, and the outcome reported under its id. An unreached mutation
# is reported `unknown`, never as a pass. This is the only way to run a mutation (#1708): no
# `mutate` file to write, no hand-made worktree, no hand-written ledger row.
#
#   witness-check.sh --worktree <reviewed tree> --id <id> --test <command>
#                    (--file <path> --old <string> --new <string> | --patch <file>)
#                    (--repo <repo> --ticket <n> [--round <k>] [--ledger <path>] | --no-ledger)
#                    [--slots <k>] [--baseline-seconds <s> | --timeout <s>]
#                    [--call-site | --worker]
#
# `--file` is a path inside the reviewed tree (relative, tracked at HEAD); `--old` is replaced by
# `--new` once, literally: bytes only, no regex, no escapes, no shell, no newline stripped. `--old`
# that does not occur exactly once in HEAD's copy of the file (overlapping occurrences count) is
# refused with exit 2 before any worktree exists and writes no ledger row. `--new ''` deletes.
# `--patch <file>` is the same one mutation as a unified diff (`git apply` at HEAD, for
# mutation-audit/witness.sh); one that does not apply is `unknown`. `--test` is a shell command,
# run as `bash -o pipefail -c` from the witness's top level, for the covering suite only. Several
# mutations are several calls (loop in your own shell; `--slots` bounds how many run at once).
#
# `--call-site` types the ledger row call-site-mutation instead of witness-mutation, and `--worker`
# worker-mutation (a worker's own mutations, implement/SKILL.md § Build): the outcome of every row is
# this script's own, from the covering command's exit status, never a hand `--outcome` (#1969).
#
# Before the mutation lands, the witness gets the setup a fresh worktree lacks
# (#1219): PYTHONDONTWRITEBYTECODE=1 and no `__pycache__` (why: at the export
# below), and, when the witness has no `node_modules`, a symlink to the one Node
# would find from the reviewed tree (#1969): the nearest `node_modules` walking
# up from its top level, else the primary checkout's (the git common dir's
# parent), so a review run from a worktree under `.claude/worktrees/` still finds
# the checkout's. A Node suite then fails on the mutation, not a missing module.
# When none exists and HEAD's `package.json` declares dependencies, a mutation
# whose output says the module failed to load (ERR_MODULE_NOT_FOUND, Cannot
# find module) is `unknown`, never `red`. The link is shared with the reviewed
# tree, not a copy: a
# workspace package that `node_modules` links back into the tree resolves to
# the reviewed tree's files, a tool cache written through it lands there, and
# the link shows as untracked where `.gitignore` says `node_modules/`
# (docs/research/2026-10-04-witness-node-modules-symlink.md).
#
# A repo whose HEAD has a `uv.lock` gets `uv sync --frozen` run in each witness
# (#1528): its own `.venv`, never a link to the reviewed tree's, whose editable
# install would import the reviewed tree's code. With no `uv.lock` at HEAD the
# `.venv` stays unset and the run says so. `vendor` is not set up.
#
# The outcome is the covering command's own exit status, `pipefail` set: a command piped
# through `tail` reports the test's status, not the filter's (#1969). A reader that exits
# early (`head`, `grep -q`) can SIGPIPE the test: status 141 reads `unknown`; write the
# output to a file instead. A command that fails having printed nothing has no message to read
# and is `unknown` too.
#
# The covering command's suite runs under a time limit (#1854); SKILL.md § 4 *The time
# limit* gives the reason. `--baseline-seconds <s>` (the unmutated run's own
# time) sets it to 3x that, 60 s at least; with neither flag it is 240 s, said
# in the output; `--timeout <s>` sets it outright, and not with a baseline. A
# mutant that reached its suite and hit the limit reads `red (timeout)`, its
# ledger row is `red` with `timeout: true`, and its process group is killed.
#
# Calls run alone or side by side: each takes one of `k` slots, a flock on a file under
# `~/.cache/agent-reviews/.witness-slots/`, and waits for one rather than refusing. `k` is a third of
# the box's headroom under the 28-claude cap, 4 at most and 1 when the process table cannot be
# read, lowered to `--slots` when that is smaller (SKILL.md § 4 *The bound*).
#
# Each run with `--repo` first prunes the repo's cache-home `witness.*`
# directories older than 7 days (#1547); the code below says how.
#
# Per-call cost (#1708): every call makes its own worktree and setup, so a repeat call pays it
# again rather than sharing a tree whose earlier mutation could leak into the next. What that
# costs is measured in the PR that introduced this form.
#
# Exit: 0 the mutation was run and reported (red, HOLLOW or unknown — read the
# output); 1 setup failed before it ran; 2 bad arguments; 3 a throwaway worktree could not be
# removed and is still registered; 4 the ledger row was refused; 130 interrupted.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() { sed -n '/^#   witness-check.sh/,/^#$/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# //' >&2; exit 2; }
die() { echo "witness check: $*" >&2; exit 2; }
kind=witness-mutation
worktree="" id="" file="" old="" new="" patch="" test_cmd="" have_old=0 have_new=0
no_ledger=0 repo_name="" max_slots="" limit="" baseline=""
ledger_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --worktree) worktree="${2-}"; shift 2 || usage ;;
    --id) id="${2-}"; shift 2 || usage ;;
    --file) file="${2-}"; shift 2 || usage ;;
    --old) [ $# -ge 2 ] || usage; old="$2"; have_old=1; shift 2 ;;
    --new) [ $# -ge 2 ] || usage; new="$2"; have_new=1; shift 2 ;;
    --patch) patch="${2-}"; shift 2 || usage ;;
    --test) [ $# -ge 2 ] || usage; test_cmd="$2"; shift 2 ;;
    --repo|--ticket|--round|--ledger) [ $# -ge 2 ] || usage; ledger_args+=( "$1" "$2" )
      [ "$1" = --repo ] && repo_name="$2"; shift 2 ;;
    --slots)
      case "${2-}" in ''|*[!0-9]*|0) die "--slots needs a positive integer, got '${2-}'" ;; esac
      max_slots="$2"; shift 2 ;;
    --timeout|--baseline-seconds)
      case "${2-}" in ''|*[!0-9]*|0) die "$1 needs a positive integer, got '${2-}'" ;; esac
      if [ "$1" = --timeout ]; then limit="$2"; else baseline="$2"; fi; shift 2 ;;
    --no-ledger) no_ledger=1; shift ;;
    --worker) [ "$kind" = call-site-mutation ] || kind=worker-mutation; shift ;;
    --call-site) kind=call-site-mutation; shift ;;
    *) echo "witness check: unknown argument '$1'" >&2; usage ;;
  esac
done
[ -n "$worktree" ] || die "--worktree is required"
[ -n "$id" ] || die "--id is required"
# An id names a directory and an output file, so it is checked before anything exists: a pytest
# nodeid (`tests/a.py::t1[x]`) would put the output file inside its own worktree. Refused by
# name — map the test to a short id and report the mapping — never mangled. A `*` reaches here
# only when the caller's shell left it unexpanded, and is refused the same way.
case "$id" in *[!A-Za-z0-9._-]*) die "'$id' is not usable as a mutation id (letters, digits, . - _)" ;; esac
[ -n "$test_cmd" ] || die "--test is required: the command that runs only the covering suite"
if [ -n "$patch" ]; then
  [ -z "$file" ] && [ "$have_old" -eq 0 ] && [ "$have_new" -eq 0 ] || die "--patch and --file/--old/--new: not both, a call is one mutation"
  [ -f "$patch" ] && [ -r "$patch" ] || die "cannot read patch '$patch'"
  patch=$(realpath "$patch")
else
  [ -n "$file" ] && [ "$have_old" -eq 1 ] && [ "$have_new" -eq 1 ] ||
    die "give the one mutation as --file <path> --old <string> --new <string> (--new '' deletes), or --patch <file>; --new is required"
  [ -n "$old" ] || die "--old is empty: it would occur everywhere, give the text to replace"
  [ "$old" != "$new" ] || die "--old and --new are identical: that mutation changes nothing"
  case "$file" in /*|..|../*|*/..|*/../*) die "--file '$file' must be a path inside the reviewed tree, relative and without .." ;; esac
fi
# The per-mutant limit (#1854). 240 s with nothing to scale from, so one hung mutant
# ends well inside the 600 s a foreground Bash call allows (#1921).
[ -z "$limit" ] || [ -z "$baseline" ] || die "--timeout and --baseline-seconds: not both, --timeout would silently win"
if [ -n "$limit" ]; then limit_basis="--timeout"
elif [ -n "$baseline" ]; then
  limit=$(( baseline * 3 )); [ "$limit" -ge 60 ] || limit=60; limit_basis="3x baseline $baseline s, 60 s floor"
else limit=240; limit_basis="no --baseline-seconds given; pass the unmutated run's time to scale it"; fi
# Ledger rows are the review's cost record (#1270): a run that forgot its
# --repo/--ticket would otherwise drop them silently, so skipping them is said.
if [ "$no_ledger" -eq 1 ]; then
  [ "${#ledger_args[@]}" -eq 0 ] || die "--no-ledger with ledger arguments"
else
  case " ${ledger_args[*]-} " in *" --repo "*" --ticket "*|*" --ticket "*" --repo "*) ;;
    *) die "ledger rows need --repo and --ticket (or --no-ledger)" ;;
  esac
fi
top=$(git -C "$worktree" rev-parse --show-toplevel) || exit 1
# The one occurrence is counted in HEAD's copy, the tree every witness is built from, before
# anything is created: a mutation that cannot land is refused, never run and read as a pass.
if [ -z "$patch" ]; then
  git -C "$top" cat-file -e "HEAD:$file" 2>/dev/null || die "--file '$file' is not tracked at HEAD in $top"
  occurs=$(git -C "$top" cat-file blob "HEAD:$file" | python3 "$here/witness_replace.py" count "$old") ||
    die "could not count --old in '$file'"
  [ "$occurs" -eq 1 ] || die "--old occurs $occurs times in '$file' at HEAD, not once: give enough surrounding text to match exactly one place (nothing was run, no ledger row written)"
fi

# Job control, so the background mutation is its own process group and an interrupt can reach
# the covering suite's whole process tree rather than only the wrapper shell around it.
set -m
# One home (#1324): the review cache's `<repo>` directory, where every other
# file of a review lives, rather than a /tmp directory nothing names. The
# 14-day sweep removes files only; a root kept after exit 3 is pruned by a
# later run once it is 7 days old. `--no-ledger` runs have no repo and keep `mktemp -d`.
if [ -n "$repo_name" ]; then
  # The ledger's own fold of the name (#1527), so `--repo agent-skills` lands in `skills/`.
  home_dir=$(python3 "$here/review_ledger.py" cache-dir --repo "$repo_name") || exit 1
  mkdir -p "$home_dir" || exit 1
  # Prune first (#1547): a killed run is the case the exit sweep misses. A
  # worktree git still lists goes through `git worktree remove`; a directory it
  # does not list (a gitdir already gone) has no registration to leave behind,
  # so `rm` is safe. A failure keeps the directory and says so, and never stops
  # the review. `-mmin +10080` is exactly 7 days; `-mtime +7` would be 8.
  if stale_list=$(find "$home_dir" -mindepth 1 -maxdepth 1 -type d -name 'witness.*' -mmin +10080 2>&1); then
    while IFS= read -r stale; do
      [ -n "$stale" ] || continue
      stale_ok=1
      for w in "$stale"/worktrees/*/; do
        [ -d "$w" ] || continue
        if git -C "$worktree" worktree list --porcelain | grep -qxF "worktree ${w%/}"; then
          git -C "$worktree" worktree remove --force "${w%/}" || stale_ok=0
        else
          rm -rf "$w" || stale_ok=0
        fi
      done
      if [ "$stale_ok" -eq 1 ] && rm -rf "$stale"; then :
      elif [ -d "$stale" ]; then
        echo "witness check: could not prune $stale - kept, remove its worktrees by hand" >&2
      fi
    done <<<"$stale_list"
  else
    echo "witness check: could not list $home_dir for stale witness directories: $stale_list" >&2
  fi
  root=$(mktemp -d "$home_dir/witness.XXXXXX") || exit 1
else
  root=$(mktemp -d) || exit 1
fi
# Checked, not assumed: a TMPDIR (or HOME) under the reviewed tree would put the
# throwaway worktree inside the checkout, and that untracked directory then
# blocks `git worktree remove` and `ship` long after the review reported green.
case "$root" in "$top"/*)
  rmdir "$root"
  echo "witness check: the worktree root is inside the checkout ($root)" >&2; exit 1;;
esac
mkdir -p "$root/worktrees" || exit 1
witness="$root/worktrees/$id"
out="$root/output"
echo "witness check: per-mutant limit $limit s ($limit_basis)"
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
# Armed before the first `worktree add`, because a witness check that WORKS makes the covering
# suite fail: that failure is the ordinary outcome. INT and TERM as well: this run is minutes
# long, so a reviewer's ctrl-C is an ordinary way for it to end, and it would otherwise leave a
# registered worktree behind to stall the next `worktree remove` and any later `merge-cleanup`.
# Signalling this shell does not reach its background child, so without this the covering suite
# keeps running after its worktree is force-removed, holding the box and writing into deleted
# paths. Stop it, reap it, and only then clean up.
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
# The worker count a brief states binds this run too (`--slots`), never raises it.
[ -z "$max_slots" ] || [ "$slots" -le "$max_slots" ] || slots="$max_slots"
# A slot is a flock on one of `slots` files, held until this run exits, so calls started side by
# side by one reviewer (or by the three axes) never exceed the bound, and a call over the bound
# waits for a slot instead of declining: a witness check that refuses because the machine is
# loaded is worse than a slow one. The covering command is started without the descriptor, so a
# process it leaves behind never holds a slot.
slot_dir="${HOME:-/tmp}/.cache/agent-reviews/.witness-slots"
mkdir -p "$slot_dir" || { echo "witness check: cannot create $slot_dir" >&2; exit 1; }
while :; do
  for n in $(seq 1 "$slots"); do
    exec {slot_fd}>"$slot_dir/slot.$n" || { echo "witness check: cannot open a slot file in $slot_dir" >&2; exit 1; }
    if flock -n "$slot_fd"; then break 2; fi
    exec {slot_fd}>&-
  done
  sleep 0.2
done
# Never write bytecode in a witness. Python trusts a .pyc whose recorded source
# mtime (to the second) and size match, so a body that runs its suite, makes a
# same-size edit and runs it again inside one second reads the first run's
# bytecode and reports HOLLOW for a test that would have gone red.
export PYTHONDONTWRITEBYTECODE=1
# The witness setup a fresh worktree lacks. Any failure leaves the mutation
# unreached, so it is reported `unknown`.
# The `node_modules` Node would find for the reviewed tree (#1969), or empty: the nearest one
# walking up from its top level, else the primary checkout's.
nm_source=""
dir="$top"
while :; do
  if [ -d "$dir/node_modules" ]; then nm_source="$dir/node_modules"; break; fi
  [ "$dir" != / ] || break
  dir=$(dirname "$dir")
done
if [ -z "$nm_source" ] && common=$(git -C "$worktree" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) &&
   [ -d "$(dirname "$common")/node_modules" ]; then
  nm_source="$(dirname "$common")/node_modules"
fi
# A tree that declares dependencies and has no `node_modules` to link: a Node suite in it
# cannot load its modules, which the report below reads.
nm_missing=0
if [ -z "$nm_source" ] && git -C "$worktree" cat-file -e HEAD:package.json 2>/dev/null &&
   git -C "$worktree" show HEAD:package.json | grep -Eq '"(dependencies|devDependencies)"'; then
  nm_missing=1
  echo "witness check: package.json declares dependencies but no node_modules was found from $top or the primary checkout - a mutation that cannot load a module reads unknown" >&2
fi
prepare() { # <witness>
  find "$1" -name __pycache__ -type d -prune -exec rm -rf {} + || {
    echo "witness check: could not clear __pycache__ in $1" >&2; return 1; }
  if [ -n "$nm_source" ] && [ ! -e "$1/node_modules" ] && [ ! -L "$1/node_modules" ]; then
    ln -s "$nm_source" "$1/node_modules" || {
      echo "witness check: could not link node_modules into $1" >&2; return 1; }
  fi
  # `uv sync` in the witness itself (#1528); the header says why never a link.
  # `--frozen` installs the lock as committed and never rewrites it, and an
  # inherited UV_PROJECT_ENVIRONMENT is dropped so the `.venv` is the witness's
  # own. A failed sync leaves the mutation unreached: `unknown`, never a pass.
  if [ -f "$1/uv.lock" ]; then
    (cd "$1" && env -u UV_PROJECT_ENVIRONMENT uv sync --frozen --quiet) || {
      echo "witness check: uv sync failed in $1" >&2; return 1; }
  fi
}
# Said once per run and read from HEAD, the tree the witness is built from, so it agrees with
# the sync: a Python suite that needs a `.venv` fails for that reason, and the reviewer should be
# told it was never set up.
git -C "$worktree" cat-file -e HEAD:uv.lock 2>/dev/null ||
  echo "witness check: no uv.lock at HEAD - .venv is left unset in the witness" >&2

# The mutation lands, then the covering command runs, in that order and nowhere else. `reached`
# is set on the line before the command starts: a witness that never got that far (a worktree
# that failed to create, a setup that failed, a patch that did not apply) is `unknown`, whatever
# the exit status of what did run.
reached=0 status="" timed_out=0
started=$(date +%s)
if git -C "$worktree" worktree add --detach -q "$witness" HEAD && prepare "$witness"; then
  applied=0
  if [ -n "$patch" ]; then
    if git -C "$witness" apply "$patch" >"$out" 2>&1; then applied=1
    else echo "witness check: the patch does not apply at HEAD" >>"$out"; fi
  else
    python3 "$here/witness_replace.py" apply "$witness/$file" "$old" "$new" >"$out" 2>&1 && applied=1
  fi
  if [ "$applied" -eq 1 ]; then
    reached=1
    : >"$out"
    # CARGO_TARGET_DIR: the worktree isolates the tree, not cargo's build, and a shared target
    # dir leaves a mutated build for the next run (#1696). `timeout` leaves this job's group, so
    # an interrupt reaches it only through the trap, which signals the group.
    suite_started=$(date +%s)
    ( cd "$witness" && exec env CARGO_TARGET_DIR="$witness/target" timeout -k 5 "$limit" bash -o pipefail -c "$test_cmd" \
        </dev/null >"$out" 2>&1 {slot_fd}>&- ) &
    tp=$!
    wait "$tp"; status=$?
    while kill -0 "$tp" 2>/dev/null; do wait "$tp"; status=$?; done
    # 124 (TERM) or 137 (KILL after 5 s) counts as the timeout only when the suite itself ran for
    # the whole limit: the same status earlier is the suite's own.
    case "$status" in 124|137) [ "$(( $(date +%s) - suite_started ))" -ge "$limit" ] && timed_out=1 ;; esac
  fi
fi
seconds=$(( $(date +%s) - started ))

# A mutation's own output, head AND tail, every line tagged with the id that produced it: pytest
# puts the assertion text at the end, so the head alone cuts out exactly what you are reading for.
show() {
  n=$(wc -l <"$out" 2>/dev/null || echo 0)
  if [ "$n" -le 50 ]; then cat "$out"
  else head -25 "$out"
       printf '... %s lines omitted from the middle ...\n' "$(( n - 50 ))"
       tail -25 "$out"
  fi 2>/dev/null | awk -v p="  $id| " '{print p $0}'
}
mkdir -p "$root/outcome" || exit 1
outcome=unknown
if [ "$reached" -eq 0 ]; then
  printf '%s: unknown — it never reached its covering command, whatever it exited with\n' "$id"
  show   # what it said on the way: a patch that did not apply, a replacement that did not land
elif [ "$timed_out" -eq 1 ]; then
  printf '%s: red (timeout) — still running at the %s s limit and killed, so the tests noticed; its output so far follows\n' "$id" "$limit"
  show; outcome="red (timeout)"
else
  # 126 and 127 are the kernel answering directly: the command was not executable, or was not
  # found, so it never started. Where a real answer exists, take it instead of inferring.
  case "$status" in
    126|127) printf '%s: unknown — its covering command never executed (not found, or not executable)\n' "$id"; show ;;
    0) printf '%s: HOLLOW — the assertion still passed with its constraint stripped\n' "$id"; outcome=green ;;
    141) printf '%s: unknown — SIGPIPE: a pipe reader closed early, so the exit status is not the test'"'"'s; write the output to a file\n' "$id"; show ;;
    [1-9]*)
      if [ "$nm_missing" -eq 1 ] && grep -Eq 'ERR_MODULE_NOT_FOUND|Cannot find (module|package)' "$out"; then
        printf '%s: unknown — the module failed to load and no node_modules exists to link; not a red\n' "$id"; show
      elif [ ! -s "$out" ]; then
        # A red is read by its message (defect class 3); one that printed nothing has none to read.
        printf '%s: unknown — the covering command failed (exit %s) but printed nothing, so there is no assertion to read\n' "$id" "$status"
      else
        printf '%s: red — its own message follows; confirm it is your assertion, not a missing file or a denied path\n' "$id"
        show; outcome=red
      fi ;;
    *) printf '%s: unknown — the mutation never ran to completion; report it by name, never as a pass\n' "$id" ;;
  esac
fi
# One ledger row (#1270), written here because cleanup removes the files. The outcome is the word
# the report above wrote, so the mapping from exit status to outcome has this one home; a missing
# outcome file or wall clock is refused by `append`, never written as a stand-in.
append_failed=0
if [ "$no_ledger" -eq 0 ]; then
  printf '%s\n' "$outcome" >"$root/outcome/$id"
  python3 "$here/review_ledger.py" append "${ledger_args[@]}" --type "$kind" \
    --mutation-id "$id" --status-file "$root/outcome/$id" --seconds "$seconds" || append_failed=1
fi
cleanup || exit 3
trap - EXIT INT TERM
[ "$append_failed" -eq 0 ] || { echo "witness check: 1 mutation row(s) not appended - put the refusal above on the first line of your summary" >&2; exit 4; }
exit 0
