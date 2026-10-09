#!/usr/bin/env bash
# Test for #1503 and #1510: tests/all.sh runs every `*_test.py` as
# `uv run pytest <file>`, and fails the run on a `*_test.py` that imports
# `unittest` (`unittest.mock` included), naming the file, or from which pytest
# collects no tests (exit 5). Every case runs the working tree's tests/all.sh,
# with the repo's pyproject.toml and uv.lock, in a shadow repo of fixture
# suites.
#
# The fixtures live under tests/fixtures/pytest-runner/ named without the
# `_test.py` suffix, so this repo's own gate never discovers them; each case
# copies the ones it needs in under a `*_test.py` name. Each unittest fixture's
# one test passes under pytest, so a red run of it is the unittest check's and
# no one else's.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset TESTS_JOBS TESTS_CPU_BUDGET
root=$(git rev-parse --show-toplevel) || exit 1
fixtures=$root/tests/fixtures/pytest-runner
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
# One environment for every shadow run, so each case does not build its own.
export UV_PROJECT_ENVIRONMENT=$shadow/venv
fail=0
check() { # <name> <0|1 condition status>
  if [ "$2" = 0 ]; then echo "ok   $1"; else echo "  FAIL $1"; fail=1; fi
}

# fresh <dest>=<fixture>...: a shadow repo holding tests/all.sh,
# pyproject.toml, uv.lock and each fixture at its dest path.
fresh() {
  local pair
  rm -rf "$shadow/repo"; mkdir -p "$shadow/repo/tests"
  cp "$root/tests/all.sh" "$root/pyproject.toml" "$root/uv.lock" "$shadow/repo/" || return 1
  mv "$shadow/repo/all.sh" "$shadow/repo/tests/all.sh"
  for pair in "$@"; do
    mkdir -p "$(dirname "$shadow/repo/${pair%%=*}")"
    cp "$fixtures/${pair#*=}.py" "$shadow/repo/${pair%%=*}" || return 1
  done
  git -C "$shadow/repo" init -q && git -C "$shadow/repo" add -A
}
gate() { out=$(cd "$shadow/repo" && bash tests/all.sh "$@" 2>&1); rc=$?; }
has() { grep -qF -- "$1" <<<"$out"; }

fresh a/idiom_test.py=pytest_idiom || { echo "FAIL: could not build the shadow repo"; exit 1; }
gate
check "a pytest-idiom suite goes green under pytest" "$([ "$rc" = 0 ] && has "PASS a/idiom_test.py ("; echo $?)"
check "...and the summary line counts it" "$(grep -qx '1 suites passed' <<<"$out"; echo $?)"
[ "$fail" = 0 ] || printf '%s\n' "$out"

fresh a/red_test.py=pytest_red
gate
check "a failing pytest-idiom suite goes red" "$([ "$rc" = 1 ] && has "FAIL a/red_test.py"; echo $?)"

# Each import form beside a good suite, which must not be the one named.
for form in unittest_import unittest_from_import unittest_mock_import unittest_mock_dotted_import; do
  fresh a/idiom_test.py=pytest_idiom b/old_test.py=$form
  gate
  check "$form: a *_test.py importing unittest fails the gate, naming the file" \
    "$([ "$rc" = 1 ] && has "FAIL b/old_test.py" && has "b/old_test.py imports unittest"; echo $?)"
  check "$form: ...and names only that file" "$(! has "a/idiom_test.py imports"; echo $?)"
done

# A unittest check that cannot run has not found the tree clean. A git shim
# fails only `git grep`, so the run's other git calls still work.
fresh a/idiom_test.py=pytest_idiom
mkdir -p "$shadow/bin"
printf '#!/bin/sh\n[ "$1" = grep ] && exit 128\nexec %s "$@"\n' "$(command -v git)" >"$shadow/bin/git"
chmod +x "$shadow/bin/git"
out=$(cd "$shadow/repo" && PATH=$shadow/bin:$PATH bash tests/all.sh 2>&1); rc=$?
check "a unittest check whose git grep fails stops the gate" \
  "$([ "$rc" = 2 ] && has "unittest import check could not run"; echo $?)"

fresh a/empty_test.py=zero_tests
gate
check "a *_test.py with zero collected tests fails the gate" \
  "$([ "$rc" = 1 ] && has "FAIL a/empty_test.py" && has "no tests ran"; echo $?)"

fresh a/idiom_test.py=pytest_idiom b/plain_test.py=pytest_idiom
gate --list
check "--list labels each suite by its path alone" \
  "$([ "$rc" = 0 ] && [ "$out" = $'a/idiom_test.py\nb/plain_test.py' ]; echo $?)"

# A gate with no uv must fail, not skip every pytest suite. PATH keeps only
# the system directories, which hold git, bash and python3 but not uv.
fresh a/idiom_test.py=pytest_idiom
out=$(cd "$shadow/repo" && PATH=/usr/bin:/bin bash tests/all.sh 2>&1); rc=$?
check "a missing uv fails the gate, naming uv" "$([ "$rc" != 0 ] && has "uv is not on PATH"; echo $?)"

[ "$fail" = 0 ] || { printf -- '--- last gate output ---\n%s\n' "$out"; exit 1; }
echo "ALL PASS"
