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

case "${1:-}" in
  --list) suites | cut -f1; exit 0 ;;
  "") ;;
  *) echo "usage: tests/all.sh [--list]" >&2; exit 2 ;;
esac

# A missing cargo must fail the gate, not silently skip every Cargo suite.
if suites | cut -f2 | grep -q '^cargo test ' && ! command -v cargo >/dev/null 2>&1; then
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

count=0
while IFS=$'\t' read -r label cmd; do
  if out=$($cmd 2>&1 </dev/null); then
    if hit=$(printf '%s\n' "$out" | grep -m1 -E "$failure_signature"); then
      report_failure "$label" "$out" \
        "tests/all.sh: exited 0, but its output carries a failure line:" \
        "  $hit" \
        "$(logging_remedy "$hit")"
    fi
    echo "PASS $label"
    count=$((count + 1))
  else
    report_failure "$label" "$out"
  fi
done < <(suites)

echo "$count suites passed"
