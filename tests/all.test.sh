#!/usr/bin/env bash
# Regression test for #620: a caller's leaked GIT_DIR/GIT_WORK_TREE/
# GIT_INDEX_FILE/GIT_COMMON_DIR/GIT_OBJECT_DIRECTORY/
# GIT_ALTERNATE_OBJECT_DIRECTORIES must not let this repo's suite touch that
# caller's repo. Reproduces the incident by copying the working tree of this
# repo into a scratch git repo (so it carries any uncommitted fix to
# tests/all.sh, not just what's in HEAD) and running its own tests/all.sh
# with the leak pointed at a separate victim repo, as it did on 2026-09-07.
#
# Guarded against re-entrant recursion: this file is itself discovered by
# the nested tests/all.sh invocation below, so it no-ops on that pass —
# gated on a sentinel value we mint ourselves, not merely on the variable
# being set, so a stray GIT_ENV_SCRUB_TEST_ACTIVE left in the environment by
# something else fails loudly instead of silently reading as a skip/PASS.
#
# Copies the working tree (never the .git dir) into the shadow: this
# checkout may itself be a linked worktree, whose .git is a pointer file
# back at the main repo's shared git dir — copying it verbatim would let a
# leak in the shadow corrupt the real repo we're sitting in. The shadow gets
# its own fresh `git init`, and the victim is a second, unrelated scratch
# repo the leak actually points the env at, so a corruption is something we
# can observe on a repo the run had no business touching.
set -uo pipefail

_nested_sentinel="git-env-scrub-nested-pass"

if [ "${GIT_ENV_SCRUB_TEST_ACTIVE:-}" = "$_nested_sentinel" ]; then
  echo "SKIP (nested pass)"
  exit 0
fi
if [ -n "${GIT_ENV_SCRUB_TEST_ACTIVE:-}" ]; then
  echo "FAIL: GIT_ENV_SCRUB_TEST_ACTIVE is already set in the environment to an unexpected value; a stray leak must not be read as a nested SKIP/PASS"
  exit 1
fi

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root="$(git rev-parse --show-toplevel)"

shadow=$(mktemp -d)
victim=$(mktemp -d)
trap 'rm -rf "$shadow" "$victim"' EXIT

(cd "$root" && tar -c --exclude=.git .) | (cd "$shadow" && tar -x) \
  || { echo "FAIL: could not copy the working tree into the shadow"; exit 1; }
git -C "$shadow" init -q \
  || { echo "FAIL: could not init the shadow repo"; exit 1; }
git -C "$shadow" add -A \
  && git -C "$shadow" -c user.email=t@example.com -c user.name=t commit -q -m shadow \
  || { echo "FAIL: could not commit the shadow working tree"; exit 1; }

git init -q "$victim" \
  || { echo "FAIL: could not init the victim repo"; exit 1; }

out=$(
  cd "$shadow" &&
    GIT_ENV_SCRUB_TEST_ACTIVE="$_nested_sentinel" \
    GIT_DIR="$victim/.git" GIT_WORK_TREE="$victim" GIT_INDEX_FILE="$victim/.git/index" \
    bash "$shadow/tests/all.sh" 2>&1
)
rc=$?

if [ "$rc" != 0 ]; then
  echo "FAIL: nested tests/all.sh exited $rc under a leaked GIT_DIR"
  printf '%s\n' "$out"
  exit 1
fi
if ! printf '%s\n' "$out" | grep -qE '^[1-9][0-9]* suites passed$'; then
  echo "FAIL: nested tests/all.sh reported no suites run — it must have resolved its root against the leaked/victim repo instead of the shadow working tree"
  printf '%s\n' "$out"
  exit 1
fi
echo "ALL PASS"
