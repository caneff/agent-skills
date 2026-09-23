#!/usr/bin/env bash
# #1092: the sweep in tests/lane-unparked.test.sh reads the commit
# (`git ls-tree`), which no index write can change. That was the ticket's
# hypothesis for its intermittent "swept set does not contain <file>"; the
# flake was really `printf | grep -q` under pipefail (SIGPIPE), checked
# at the end of this file.
#
# This runs the real test in a throwaway clone whose index is blanked, the
# extreme of a partial listing: it must still pass. Its guard is the reverse
# control: the same clone with a file deleted from HEAD's tree must fail, so
# a test that passes because it swept nothing is caught.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)" || exit 1
trap 'rm -rf "$scratch"' EXIT
fail=0

git clone -q --no-hardlinks "$root" "$scratch/c" || { echo "FAIL: clone" >&2; exit 1; }
# Test the working copy's script (the clone's files are HEAD's).
cp "$root/tests/lane-unparked.test.sh" "$scratch/c/tests/lane-unparked.test.sh"
cd "$scratch/c" || exit 1

: >.git/index   # an index that lists nothing
out="$(bash tests/lane-unparked.test.sh 2>&1)"; st=$?
if [ "$st" -ne 0 ]; then
  echo "FAIL: sweep depends on the index; blank index gave exit $st: $out" >&2; fail=1
fi

# Reverse control: HEAD's tree loses a must-sweep member -> the test must fail.
git read-tree HEAD && git rm -q --cached burndown/references/run-file.md &&
  git -c user.email=t@example.com -c user.name=t commit -qm drop || { echo "FAIL: control setup" >&2; exit 1; }
: >.git/index
out="$(bash tests/lane-unparked.test.sh 2>&1)"; st=$?
if [ "$st" -eq 0 ] || ! grep -q 'does not contain burndown/references/run-file.md' <<<"$out"; then
  echo "FAIL: control: dropping a member from HEAD did not trip the must-sweep check (exit $st): $out" >&2; fail=1
fi

# The flake's actual cause: a `| grep -q` pipeline under pipefail. Static, since
# the failure is probabilistic (5 in 300 runs) and cannot be asserted directly.
if grep -nE '\|[[:space:]]*grep[^|]*-[a-zA-Z]*q' "$root/tests/lane-unparked.test.sh" | grep -v '^[0-9]*:[[:space:]]*#'; then
  echo "FAIL: tests/lane-unparked.test.sh pipes into grep -q under pipefail (SIGPIPE flake)" >&2; fail=1
fi

[ "$fail" = 0 ] && echo "ok — lane-unparked sweeps the commit, not the index"
exit "$fail"
