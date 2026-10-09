#!/usr/bin/env bash
# Test for #1503: tests/all.sh runs each `*_test.py` as `uv run pytest <file>`,
# except the files tests/pytest-transitional.txt lists, which still run as
# `python3 <file>`; a list entry naming no tracked `*_test.py` fails the gate,
# naming the entry. Every case runs the working tree's tests/all.sh, with the
# repo's pyproject.toml and uv.lock, in a shadow repo of fixture suites.
#
# The fixtures live under tests/fixtures/pytest-runner/ named without the
# `_test.py` suffix, so this repo's own gate never discovers them; each case
# copies the ones it needs in under a `*_test.py` name. Each fixture can only
# pass under one runner (its header says how), so a green run says which
# runner ran it, not only that something exited 0.
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

# fresh <list contents> <dest>=<fixture>...: a shadow repo holding tests/all.sh,
# pyproject.toml, uv.lock, the given list and each fixture at its dest path.
fresh() {
  local list=$1 pair; shift
  rm -rf "$shadow/repo"; mkdir -p "$shadow/repo/tests"
  cp "$root/tests/all.sh" "$root/pyproject.toml" "$root/uv.lock" "$shadow/repo/" || return 1
  mv "$shadow/repo/all.sh" "$shadow/repo/tests/all.sh"
  printf '%s' "$list" >"$shadow/repo/tests/pytest-transitional.txt"
  for pair in "$@"; do
    mkdir -p "$(dirname "$shadow/repo/${pair%%=*}")"
    cp "$fixtures/${pair#*=}.py" "$shadow/repo/${pair%%=*}" || return 1
  done
  git -C "$shadow/repo" init -q && git -C "$shadow/repo" add -A
}
gate() { out=$(cd "$shadow/repo" && bash tests/all.sh "$@" 2>&1); rc=$?; }
has() { grep -qF -- "$1" <<<"$out"; }

fresh $'# a comment\n\n' a/idiom_test.py=pytest_idiom || { echo "FAIL: could not build the shadow repo"; exit 1; }
gate
check "a pytest-idiom suite not on the list goes green under pytest" "$([ "$rc" = 0 ] && has "PASS a/idiom_test.py ("; echo $?)"
check "...and the summary line counts it" "$(grep -qx '1 suites passed' <<<"$out"; echo $?)"
[ "$fail" = 0 ] || printf '%s\n' "$out"

fresh '' a/red_test.py=pytest_red
gate
check "a failing pytest-idiom suite not on the list goes red" "$([ "$rc" = 1 ] && has "FAIL a/red_test.py"; echo $?)"

fresh $'# #1\na/listed_test.py\n' a/listed_test.py=python3_only
gate
check "a suite on the list runs under python3" "$([ "$rc" = 0 ] && has "PASS a/listed_test.py ("; echo $?)"

fresh '' a/listed_test.py=python3_only
gate
check "...and the same suite off the list runs under pytest, which fails it" "$([ "$rc" = 1 ] && has "FAIL a/listed_test.py"; echo $?)"

fresh $'a/idiom_test.py\nb/gone_test.py\n' a/idiom_test.py=pytest_idiom
gate
check "a list entry naming no tracked suite fails the gate" "$([ "$rc" != 0 ]; echo $?)"
check "...naming the entry" "$(has "b/gone_test.py"; echo $?)"
gate --list
check "...and fails --list as well" "$([ "$rc" != 0 ] && has "b/gone_test.py"; echo $?)"

fresh $'a/idiom_test.py\n' a/idiom_test.py=pytest_idiom b/plain_test.py=pytest_idiom
gate --list
check "--list labels each suite by its path alone, either runner" \
  "$([ "$rc" = 0 ] && [ "$out" = $'a/idiom_test.py\nb/plain_test.py' ]; echo $?)"

# A gate with no uv must fail, not skip every pytest suite. PATH keeps only
# the system directories, which hold git, bash and python3 but not uv.
fresh '' a/idiom_test.py=pytest_idiom
out=$(cd "$shadow/repo" && PATH=/usr/bin:/bin bash tests/all.sh 2>&1); rc=$?
check "a missing uv fails the gate, naming uv" "$([ "$rc" != 0 ] && has "uv is not on PATH"; echo $?)"

[ "$fail" = 0 ] || { printf -- '--- last gate output ---\n%s\n' "$out"; exit 1; }
echo "ALL PASS"
