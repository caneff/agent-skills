#!/usr/bin/env bash
# kit.sh at its command line: a sudoku-kit checkout without the guide library
# (src/sudoku_kit/guide_file.py) is refused, naming SUDOKU_KIT and spec-127;
# one with it runs the command. The run case uses a stand-in checkout whose
# pyproject has no dependencies, so it needs no network and no real sudoku-kit.
# Blind to: the library's own behaviour.
set -u
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0

mkdir -p "$tmp/old/src/sudoku_kit"
out=$(SUDOKU_KIT="$tmp/old" bash "$here/kit.sh" python -c 'print("ran")' 2>&1)
rc=$?
if [ "$rc" -ne 2 ] || [[ "$out" != *SUDOKU_KIT* ]] || [[ "$out" != *spec-127* ]] || [[ "$out" == *ran* ]]; then
  echo "FAIL: a checkout without guide_file.py was not refused (rc=$rc): $out"; fail=1
fi

out=$(SUDOKU_KIT="$tmp/missing" bash "$here/kit.sh" python -c 'print("ran")' 2>&1)
rc=$?
if [ "$rc" -ne 2 ] || [[ "$out" != *"no checkout at $tmp/missing"* ]] || [[ "$out" == *ran* ]]; then
  echo "FAIL: a missing checkout was not refused as missing (rc=$rc): $out"; fail=1
fi

mkdir -p "$tmp/new/src/sudoku_kit"
touch "$tmp/new/src/sudoku_kit/guide_file.py"
printf '[project]\nname = "stand-in"\nversion = "0"\nrequires-python = ">=3.10"\ndependencies = []\n' > "$tmp/new/pyproject.toml"
out=$(cd "$tmp" && SUDOKU_KIT="$tmp/new" bash "$here/kit.sh" python -c 'import os; print("ran in", os.getcwd())' 2>/dev/null)
rc=$?
if [ "$rc" -ne 0 ] || [ "$out" != "ran in $tmp" ]; then
  echo "FAIL: a checkout with the library did not run the command in the caller's directory (rc=$rc): $out"; fail=1
fi

[ "$fail" -eq 0 ] && echo "ok: kit.sh refuses a missing checkout and one without the guide library, and runs one with it"
exit "$fail"
