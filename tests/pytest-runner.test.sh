#!/usr/bin/env bash
# The end-to-end test of spec #1494 (pytest everywhere, ADR 0007), at the seam
# AGENTS.md names, `bash tests/all.sh`. In a shadow repo of fixture suites it
# runs the working tree's tests/all.sh, with the repo's pyproject.toml and
# uv.lock, and checks that every `*_test.py` runs as `uv run --locked pytest
# <file>` (#1503), that the run fails on a `*_test.py` importing `unittest`,
# `unittest.mock` included and in any spelling, naming the file, and on one
# from which pytest collects no tests (exit 5, #1510), that a check which
# cannot read the suites stops the run, and that labels and the summary line
# keep their shape. On this repo's own tree it checks that no tracked suite
# imports unittest and that both testing skills state the ruling (#1511).
#
# Blind to: whether a model reading python-testing-patterns or
# setup-python-repo then writes its next test as pytest, which only a reading
# of those files judges; and anything about the real suites beyond what the
# gate's own run of them shows (that each passes and collects at least one
# test is the run of `bash tests/all.sh` itself, not this file).
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

# fresh <dest>=<fixture>...: a shadow repo holding tests/all.sh, its unittest
# check, pyproject.toml, uv.lock and each fixture at its dest path.
fresh() {
  local pair
  rm -rf "$shadow/repo"; mkdir -p "$shadow/repo/tests"
  cp "$root/tests/all.sh" "$root/pyproject.toml" "$root/uv.lock" "$shadow/repo/" || return 1
  mv "$shadow/repo/all.sh" "$shadow/repo/tests/all.sh"
  cp "$root/tests/unittest_imports.py" "$shadow/repo/tests/" || return 1
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
for form in unittest_import unittest_from_import unittest_mock_import unittest_mock_dotted_import \
    unittest_comma_import unittest_paren_import unittest_dynamic_import; do
  fresh a/idiom_test.py=pytest_idiom b/old_test.py=$form
  gate
  check "$form: a *_test.py importing unittest fails the gate, naming the file" \
    "$([ "$rc" = 1 ] && has "FAIL b/old_test.py" && has "b/old_test.py imports unittest"; echo $?)"
  check "$form: ...and names only that file" "$(! has "a/idiom_test.py imports"; echo $?)"
done

# A unittest check that cannot run has not found the tree clean: a suite it
# cannot parse, and a `git ls-files -z` that fails (a git shim fails only that
# call, the check's own, so the run's other git calls still work).
fresh a/idiom_test.py=pytest_idiom b/broken_test.py=unparsable
gate
check "a suite the unittest check cannot parse stops the gate, naming it" \
  "$([ "$rc" = 2 ] && has "unittest import check could not run" && has "b/broken_test.py"; echo $?)"
fresh a/idiom_test.py=pytest_idiom
mkdir -p "$shadow/bin"
printf '#!/bin/sh\n[ "$1" = ls-files ] && [ "$2" = -z ] && exit 128\nexec %s "$@"\n' "$(command -v git)" >"$shadow/bin/git"
chmod +x "$shadow/bin/git"
out=$(cd "$shadow/repo" && PATH=$shadow/bin:$PATH bash tests/all.sh 2>&1); rc=$?
check "a unittest check whose git ls-files fails stops the gate" \
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
check "a missing uv fails the gate, naming uv and how to get it" "$([ "$rc" != 0 ] && has "uv is not on PATH" && has "install uv"; echo $?)"

# This repo's own tree: no tracked suite imports unittest, and both testing
# skills state the ruling and cite ADR 0007 by a path that resolves anywhere.
out=$(cd "$root" && python3 tests/unittest_imports.py 2>&1); rc=$?
check "no tracked *_test.py in this repo imports unittest" "$([ "$rc" = 0 ] && [ -z "$out" ]; echo $?)"
for skill in python-testing-patterns setup-python-repo; do
  check "$skill states the pytest ruling, citing ADR 0007" \
    "$(grep -qF '~/.agents/skills/docs/adr/0007-pytest-everywhere.md' "$root/$skill/SKILL.md"; echo $?)"
done

[ "$fail" = 0 ] || { printf -- '--- last gate output ---\n%s\n' "$out"; exit 1; }
echo "ALL PASS"
