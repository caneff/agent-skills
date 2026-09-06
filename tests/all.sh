#!/usr/bin/env bash
# Runs every test suite in the repo: git-tracked *.test.sh, every audit.py
# that implements --selfcheck, and every test_audit.py. One line per suite;
# exits non-zero on the first failure (and prints that suite's output).
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

count=0

run() { # run <label> <cmd...>
  local label=$1; shift
  local out
  if out=$("$@" 2>&1 </dev/null); then
    echo "PASS $label"
    count=$((count + 1))
  else
    echo "FAIL $label"
    printf '%s\n' "$out"
    exit 1
  fi
}

while IFS= read -r f; do
  run "$f" bash "$f"
done < <(git ls-files -- '*.test.sh')

while IFS= read -r f; do
  grep -q -- '--selfcheck' "$f" && run "$f --selfcheck" python3 "$f" --selfcheck
done < <(git ls-files | grep -E '(^|/)audit\.py$')

while IFS= read -r f; do
  run "$f" python3 "$f"
done < <(git ls-files | grep -E '(^|/)test_audit\.py$')

echo "$count suites passed"
