#!/usr/bin/env bash
# Regression test for #620: a caller's leaked GIT_DIR/GIT_WORK_TREE/
# GIT_INDEX_FILE/GIT_COMMON_DIR/GIT_OBJECT_DIRECTORY/
# GIT_ALTERNATE_OBJECT_DIRECTORIES must not let this repo's suite touch that
# caller's repo. Reproduces the incident of 2026-09-07 in a scratch repo that
# holds only tests/all.sh and one probe suite that writes through git, run
# with the leak pointed at a separate victim repo. The probe is what makes a
# leak observable: with the scrub gone, all.sh resolves its root against the
# victim, finds no suites there, and the probe's write would land in the
# victim. (Until #1415 the shadow was a copy of the whole tree that ran every
# suite again, 251 of the suite's 494 serial seconds, for the same three
# assertions.)
#
# Guarded against re-entrant recursion: a nested copy of this file would be
# discovered by a nested tests/all.sh, so it no-ops on that pass —
# gated on a sentinel value we mint ourselves, not merely on the variable
# being set, so a stray GIT_ENV_SCRUB_TEST_ACTIVE left in the environment by
# something else fails loudly instead of silently reading as a skip/PASS.
#
# The shadow is a fresh `git init` that gets only tests/all.sh (never the .git
# dir: this checkout may be a linked worktree whose .git is a pointer file back
# at the shared git dir), and the victim is a second, unrelated scratch repo the
# leak actually points the env at, so a corruption is something we can observe
# on a repo the run had no business touching.
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

mkdir -p "$shadow/tests"
cp "$root/tests/all.sh" "$shadow/tests/all.sh" \
  || { echo "FAIL: could not copy tests/all.sh into the shadow"; exit 1; }
# The probe writes through git: with the leak live it would land in the victim.
cat >"$shadow/probe.test.sh" <<'PROBE'
#!/usr/bin/env bash
git config --local probe.ran yes
PROBE
git -C "$shadow" init -q \
  || { echo "FAIL: could not init the shadow repo"; exit 1; }
git -C "$shadow" add -A \
  && git -C "$shadow" -c user.email=t@example.com -c user.name=t commit -q -m shadow \
  || { echo "FAIL: could not commit the shadow"; exit 1; }

git init -q "$victim" \
  || { echo "FAIL: could not init the victim repo"; exit 1; }
before_config=$(cat "$victim/.git/config")
before_ls=$(cd "$victim" && ls -A)

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

if [ "$(git -C "$shadow" config --local --get probe.ran)" != yes ]; then
  echo "FAIL: the probe suite did not write into the shadow repo, so the run did not resolve its root there"
  exit 1
fi

after_config=$(cat "$victim/.git/config")
after_ls=$(cd "$victim" && ls -A)
if [ "$before_config" != "$after_config" ] || [ "$before_ls" != "$after_ls" ]; then
  echo "FAIL: the leaked GIT_DIR let the suite rewrite or write into the victim repo it pointed at"
  exit 1
fi
echo "ALL PASS"
