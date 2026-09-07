#!/usr/bin/env bash
# Regression test for #620: a caller's leaked GIT_DIR/GIT_WORK_TREE/
# GIT_INDEX_FILE/GIT_COMMON_DIR must not let this repo's suite touch that
# caller's repo. Reproduces the incident by cloning this repo (so the leak
# points at the very repo whose suite is running, as it did on 2026-09-07)
# and running its own tests/all.sh under the leak.
#
# Guarded against re-entrant recursion: this file is itself discovered by
# the nested tests/all.sh invocation below, so it no-ops on that pass.
#
# Clones (never copies the worktree) so the shadow gets its own real .git
# directory: this checkout may itself be a linked worktree, whose .git is a
# pointer file back at the main repo's shared git dir — copying it verbatim
# would let a leak in the shadow corrupt the real repo we're sitting in.
set -uo pipefail

if [ -n "${GIT_ENV_SCRUB_TEST_ACTIVE:-}" ]; then
  echo "SKIP (nested pass)"
  exit 0
fi

root="$(git rev-parse --show-toplevel)"
shadow=$(mktemp -d)
trap 'rm -rf "$shadow"' EXIT

git clone -q --no-hardlinks "$root" "$shadow" || { echo "FAIL: could not create shadow clone"; exit 1; }
before=$(cat "$shadow/.git/config")

(
  cd "$shadow" &&
    GIT_ENV_SCRUB_TEST_ACTIVE=1 \
    GIT_DIR="$shadow/.git" GIT_WORK_TREE="$shadow" GIT_INDEX_FILE="$shadow/.git/index" \
    bash "$shadow/tests/all.sh" >/dev/null
)
rc=$?

after=$(cat "$shadow/.git/config")

if [ "$rc" != 0 ]; then
  echo "FAIL: nested tests/all.sh exited $rc under a leaked GIT_DIR"
  exit 1
fi
if [ "$before" != "$after" ]; then
  echo "FAIL: leaked GIT_DIR let the suite rewrite the caller's repo config"
  exit 1
fi
echo "ALL PASS"
