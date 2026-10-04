#!/usr/bin/env bash
# Runs every test suite in the repo. Three discovery rules over git-tracked
# files, no per-file special cases: `*.test.sh` runs under bash, `*_test.py`
# runs directly under python3, and each `audit.py` that implements
# `--selfcheck` runs with that flag. One line per suite; exits non-zero on
# the first failure (and prints that suite's output). A suite is failed on
# its exit status *or* on a failure signature at the start of a line in its
# output, because exit status alone read a suite that reported findings and
# exited 0 as green (#954; the signature set and its reason are below).
# `--list` prints the labels the rules select, without running anything.
# `--changed <base>` narrows the run to the suites under every top-level
# directory the diff `<base>...HEAD` touches plus everything under `tests/`
# (the repo-wide checks); see `scope_changed` for when it widens to the full
# suite. Suites run concurrently, `TESTS_JOBS` at a time (default `nproc`),
# and are reported in discovery order. A suite whose first twenty lines carry
# `all.sh: serial` cannot share the box (a fixed port, a shared global path):
# it runs alone after the concurrent ones, and names why on that line.
# Each suite is also held to a CPU budget (see `cpu_budget`): its own user+sys
# time with every process it started, not wall-clock time, so load on a shared
# box cannot make it flaky.
# This is the merge gate (`git config land.testcmd`), not a push hook — see
# #633.
# -f: suite commands are word-split out of the tab-separated list, so keep
# the shell from globbing a path that happens to contain a wildcard.
set -uf
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would redirect every
# git call below (and in every suite it spawns) at that caller's repo instead
# of this one (#620) — scrub before touching git at all.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1

suites() { # prints "<label>\t<command>" per discovered suite
  git ls-files -- '*.test.sh' |
    while IFS= read -r f; do printf '%s\tbash %s\n' "$f" "$f"; done
  git ls-files -- '*_test.py' |
    while IFS= read -r f; do printf '%s\tpython3 %s\n' "$f" "$f"; done
  git ls-files | grep -E '(^|/)audit\.py$' |
    while IFS= read -r f; do
      grep -q -- '--selfcheck' "$f" &&
        printf '%s --selfcheck\tpython3 %s --selfcheck\n' "$f" "$f"
    done
  git ls-files -- '*Cargo.toml' |
    while IFS= read -r f; do printf '%s\tcargo test --manifest-path %s\n' "$f" "$f"; done
}

# Which suites a `--changed <base>` run keeps. The full suite is the answer
# whenever the diff cannot be pinned to a directory that owns suites: a change
# to this script, a file at the repo root, or a directory with no suite of its
# own (nothing then says which suites cover it). An empty diff keeps only the
# repo-wide checks. Prints the kept labels' directories as a space-separated
# word list on stdout, or `*` for the full suite; the reason goes to stderr.
scope_changed() { # <base>
  local base=$1 files file dir all_dirs dirs=""
  files=$(git diff --name-only --no-renames "$base...HEAD") || {
    echo "tests/all.sh: cannot diff $base...HEAD" >&2; exit 2; }
  all_dirs=$(suites | cut -f1 | awk -F/ 'NF > 1 {print $1}' | sort -u)
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    dir=${file%%/*}
    if [ "$file" = tests/all.sh ] || [ "$dir" = "$file" ] || ! grep -qxF "$dir" <<<"$all_dirs"; then
      echo "full suite: $file is not owned by a directory with suites (or is tests/all.sh)" >&2
      echo '*'; return
    fi
    case " $dirs " in *" $dir "*) ;; *) dirs="$dirs $dir" ;; esac
  done <<<"$files"
  dirs=${dirs# }
  echo "changed suites: ${dirs:-none} + tests" >&2
  echo "$dirs"
}

filter_dirs() { # <dirs word list>: keeps suites under those dirs, under tests/, or at the root
  awk -F'\t' -v dirs=" $1 tests " '{ n = split($1, p, "/"); if (n == 1 || index(dirs, " " p[1] " ")) print }'
}

list_only=0 changed_base=""
while [ $# -gt 0 ]; do
  case "$1" in
    --list) list_only=1; shift ;;
    --changed) [ $# -ge 2 ] || { echo "usage: tests/all.sh [--list] [--changed <base>]" >&2; exit 2; }
               changed_base=$2; shift 2 ;;
    *) echo "usage: tests/all.sh [--list] [--changed <base>]" >&2; exit 2 ;;
  esac
done

selected() { # prints the "<label>\t<command>" lines this run covers
  if [ -z "$changed_base" ]; then suites; return; fi
  local dirs
  dirs=$(scope_changed "$changed_base") || exit $?
  if [ "$dirs" = '*' ]; then suites; else suites | filter_dirs "$dirs"; fi
}

if [ "$list_only" = 1 ]; then selected 2>/dev/null | cut -f1; exit "${PIPESTATUS[0]}"; fi

tmp=$(mktemp -d) || exit 1
# The selection is read once: its scope line goes to the report and a diff that
# cannot be read (exit 2) stops the run rather than selecting nothing.
selection=$(selected 2>"$tmp/scope") || { cat "$tmp/scope" >&2; rm -rf "$tmp"; exit 2; }
[ -s "$tmp/scope" ] && cat "$tmp/scope"
# A missing cargo must fail the gate, not silently skip every Cargo suite.
if printf '%s\n' "$selection" | cut -f2 | grep -q '^cargo test ' && ! command -v cargo >/dev/null 2>&1; then
  echo "tests/all.sh: cargo is not on PATH, and a tracked Cargo.toml needs it" >&2
  exit 1
fi

# A suite that exits 0 while its output opens a line with a failure word is
# defect class 1 (`docs/agents/defect-classes.md`) sitting in the harness whose
# whole job is to answer "is this tree good": `out` was captured and discarded
# on success, so a suite could print real findings, say `ok`, and be counted
# PASS (#954).
#
# Three words, anchored to the start of a line. The loose form is unusable.
# `tests/section-references.test.sh` is the worked counter-example: it prints
# `not found` four times as legitimate narration while its own mutation check
# goes red by design, so a set containing `not found` would have fired on it
# the day it was written. Running every suite and grepping its output for the
# loose set (`not found`, `missing`, `does not exist`) matched 14 suites that
# were green at the time of writing; the anchored set matched none of them.
# Re-derive rather than trust that count: run each label from `--list` and
# grep its output.
#
# The anchor doubles as the escape hatch, so no opt-out mechanism is needed: a
# suite that must reprint a child's `FAIL` line while passing indents it,
# which is also how a reader tells a quoted failure from this suite's own
# verdict.
#
# Known limit: Python's `logging.error()` writes `ERROR:root:<msg>` at column
# 0, and `2>&1` folds stderr into what is scanned here, so a green `*_test.py`
# suite that exercises a logging path is failed by this scan and cannot reach
# the indent hatch. Testing an error path is ordinary work, so this is a real
# false positive rather than a hypothetical one — recoverable, but not
# discoverable from the failure alone. `logging_remedy` below prints the two
# ways out at the moment the gate rejects such a line, because a reader whose
# green suite just went red is not reading this comment.
failure_signature='^(FAIL|Traceback|ERROR)'

# Both loop branches end a run the same way: the label, an optional note, the
# suite's whole output, exit 1.
report_failure() { # <label> <output> [<note>...]
  local label=$1 output=$2 note
  shift 2
  echo "FAIL $label"
  # Skip empty notes: a caller passing a conditional note it decided not to
  # produce would otherwise print a blank line into the failure report.
  for note in "$@"; do
    [ -n "$note" ] && printf '%s\n' "$note"
  done
  printf '%s\n' "$output"
  exit 1
}

# The known limit above is recoverable but undiscoverable: both ways out of a
# logging false positive sit in a comment nobody is reading at the moment a
# green suite goes red. Say them where that person is looking instead. Printed
# only when the matched line has the shape of a logging record
# (`LEVEL:logger:`), because on a genuine `FAIL:` catch this advice is noise
# pointing away from a real failure.
logging_remedy() { # <matched line>
  printf '%s\n' "$1" | grep -qE '^[A-Z]+:[A-Za-z0-9_.]*:' || return 0
  printf '%s\n' \
    "  That line looks like a logging record rather than this suite's own verdict." \
    "  If the suite is meant to exercise a logging path, either assert on the log" \
    "  in the test (unittest assertLogs, pytest caplog) so it never reaches stderr," \
    "  or give the logger a format that does not start the line at column 0."
}

# A suite that writes a fixture identity into the real checkout's config
# leaves every later commit authored by it (#1144: `t@example.com` sat in the
# primary checkout's config for two weeks). Snapshot the two keys before any
# suite runs and fail the suite after which they differ. `--local` reads the
# repo's own config, which is where the leak lands; an unset key reads as a
# distinct marker so an unset counts as a change. That config is shared by
# every worktree, and a concurrent legitimate change is indistinguishable from
# a leak here, so the check stays and the message names both causes (#1173).
identity_snapshot() {
  local key
  for key in user.email user.name; do
    printf '%s=%s\n' "$key" "$(git config --local --get "$key" 2>/dev/null || echo '<unset>')"
  done
}
identity_before=$(identity_snapshot)

# Concurrency (#1415): the suites run `jobs` at a time, each writing its output
# and exit status under "$tmp"; this shell reports them in discovery order, so
# the transcript reads the same as a serial run. A failure stops new suites
# from starting, lets those in flight finish (an orphaned suite would keep
# writing into a directory this script is about to remove) and exits 1. The
# identity check runs after each suite against the baseline above: suites
# overlap, so one that finishes after a leak is flagged along with the leaker,
# and the failure says so rather than naming a suite that may be innocent.
jobs=${TESTS_JOBS:-$(nproc 2>/dev/null || echo 4)}
case $jobs in ''|*[!0-9]*|0) echo "tests/all.sh: TESTS_JOBS must be a positive integer, got '$jobs'" >&2; exit 2 ;; esac

is_serial() { # <label>: a suite file whose head says `all.sh: serial`
  local file=${1%% *}
  [ -f "$file" ] && head -n 20 "$file" | grep -q 'all\.sh: serial'
}
: >"$tmp/parallel"; : >"$tmp/serial"
while IFS=$'\t' read -r label cmd; do
  [ -n "$label" ] || continue
  if is_serial "$label"; then dest=serial; else dest=parallel; fi
  printf '%s\t%s\n' "$label" "$cmd" >>"$tmp/$dest"
done <<<"$selection"
cat "$tmp/parallel" "$tmp/serial" >"$tmp/ordered"

# The CPU budget of every suite, in seconds (#1415): a suite that costs more
# fails the run, so a suite that re-runs the whole repo inside itself (the old
# tests/all.test.sh was 251 of the suite's 494 serial seconds) is a red line and
# not a quiet tax on every merge. A suite that needs more is named below with
# its own budget and a one-line reason; adding a line is the visible diff.
default_cpu_budget=15
cpu_budget() { # <label>: prints the suite's budget in seconds
  case $1 in
    flow/lane/Cargo.toml) echo 90 ;; # compiles the lane crate and runs 140+ process-spawning tests
    *) echo "${TESTS_CPU_BUDGET:-$default_cpu_budget}" ;;
  esac
}

# User+sys seconds of everything this subshell waited for, from the `times`
# builtin: line 2 is the children, descendants included. The builtin must run in
# this shell itself, so it writes to a file (a pipe or `$(...)` would run it in a
# fresh subshell that reports zero). A subshell starts at zero, so each suite
# runs in one (backgrounded, or parenthesised).
cpu_seconds() { # <file>
  times >"$1.times"
  awk '{ for (i = 1; i <= NF; i++) { split($i, p, "m"); t += p[1] * 60 + p[2] } } END { printf "%.1f", t }' "$1.times" >"$1"
}

run_suite() { # <index> <command>
  local out status after
  out=$($2 2>&1 </dev/null); status=$?
  cpu_seconds "$tmp/$1.cpu"
  after=$(identity_snapshot)
  printf '%s' "$out" >"$tmp/$1.out"
  [ "$after" = "$identity_before" ] || printf '%s' "$after" >"$tmp/$1.ident"
  echo "$status" >"$tmp/$1.rc.tmp" && mv "$tmp/$1.rc.tmp" "$tmp/$1.rc"
}

dispatch() {
  local idx=0 label cmd
  while IFS=$'\t' read -r label cmd; do
    [ -e "$tmp/stop" ] && break
    while [ "$(jobs -pr | wc -l)" -ge "$jobs" ]; do wait -n; done
    run_suite "$idx" "$cmd" &
    idx=$((idx + 1))
  done <"$tmp/parallel"
  wait
  while IFS=$'\t' read -r label cmd; do
    [ -e "$tmp/stop" ] && break
    (run_suite "$idx" "$cmd")
    idx=$((idx + 1))
  done <"$tmp/serial"
}

stop_and_wait() { touch "$tmp/stop"; wait "$dispatcher" 2>/dev/null; }
trap 'stop_and_wait; rm -rf "$tmp"' EXIT
trap 'exit 130' INT TERM
dispatch &
dispatcher=$!

count=0 idx=0
while IFS=$'\t' read -r label cmd; do
  until [ -e "$tmp/$idx.rc" ]; do
    # A dispatcher that is gone with no result for this suite never ran it:
    # that is a failure, not a pass nobody has seen (defect class 1).
    if ! kill -0 "$dispatcher" 2>/dev/null && [ ! -e "$tmp/$idx.rc" ]; then
      report_failure "$label" "" "tests/all.sh: the runner ended before this suite reported a result"
    fi
    sleep 0.05
  done
  out=$(cat "$tmp/$idx.out"); suite_status=$(cat "$tmp/$idx.rc")
  if [ -e "$tmp/$idx.ident" ]; then
    stop_and_wait
    identity_after=$(cat "$tmp/$idx.ident")
    report_failure "$label" "$out" \
      "tests/all.sh: the checkout's git identity changed while this suite ran (a fixture identity written without naming its repo, #1144):" \
      "  before: $(printf '%s' "$identity_before" | tr '\n' ' ')" \
      "  after:  $(printf '%s' "$identity_after" | tr '\n' ' ')" \
      "  Suites run concurrently, so any suite that finished after the change is flagged" \
      "  as well: the leaker is the earliest of those, or none of them, because this config is" \
      "  shared by every worktree of the repo and a session in another worktree that changed" \
      "  the identity during this run reads the same way (#1173). Re-run with TESTS_JOBS=1" \
      "  to name the suite."
  fi
  if [ "$suite_status" -eq 0 ]; then
    if hit=$(printf '%s\n' "$out" | grep -m1 -E "$failure_signature"); then
      stop_and_wait
      report_failure "$label" "$out" \
        "tests/all.sh: exited 0, but its output carries a failure line:" \
        "  $hit" \
        "$(logging_remedy "$hit")"
    fi
    cpu=$(cat "$tmp/$idx.cpu"); budget=$(cpu_budget "$label")
    if awk -v c="$cpu" -v b="$budget" 'BEGIN { exit !(c > b) }'; then
      stop_and_wait
      report_failure "$label" "$out" \
        "tests/all.sh: over its CPU budget: ${cpu}s CPU against ${budget}s (user+sys, children included)." \
        "  A suite that re-runs the repo inside itself is the usual cause. If this one really needs more," \
        "  name it in cpu_budget in tests/all.sh with its own budget and a one-line reason."
    fi
    echo "PASS $label (${cpu}s cpu)"
    count=$((count + 1))
  else
    stop_and_wait
    report_failure "$label" "$out"
  fi
  idx=$((idx + 1))
done <"$tmp/ordered"
wait "$dispatcher"

echo "$count suites passed"
