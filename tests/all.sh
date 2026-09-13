#!/usr/bin/env bash
# Runs every test suite in the repo. Three discovery rules over git-tracked
# files, no per-file special cases: `*.test.sh` runs under bash, `*_test.py`
# runs directly under python3, and each `audit.py` that implements
# `--selfcheck` runs with that flag. One line per suite; exits non-zero on
# the first failure (and prints that suite's output). `--list` prints the
# labels the rules select, without running anything. This is the merge gate
# (`git config land.testcmd`), not a push hook — see #633.
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

count=0
while IFS=$'\t' read -r label cmd; do
  if out=$($cmd 2>&1 </dev/null); then
    echo "PASS $label"
    count=$((count + 1))
  else
    echo "FAIL $label"
    printf '%s\n' "$out"
    exit 1
  fi
done < <(suites)

echo "$count suites passed"
