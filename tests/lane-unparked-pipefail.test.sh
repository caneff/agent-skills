#!/usr/bin/env bash
# #1092: tests/lane-unparked.test.sh failed intermittently under tests/all.sh
# with "the swept set does not contain <file>". The cause was
# `printf | grep -q` under pipefail: grep exits on its first match, printf
# takes SIGPIPE, and the pipeline reads as a miss (5 failures in 300 runs).
# The failure is probabilistic, so this asserts the shape statically: no
# `| grep -q` pipeline outside a comment in that test.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if grep -nE '\|[[:space:]]*grep[^|]*-[a-zA-Z]*q' "$root/tests/lane-unparked.test.sh" | grep -v '^[0-9]*:[[:space:]]*#'; then
  echo "FAIL: tests/lane-unparked.test.sh pipes into grep -q under pipefail (SIGPIPE flake)" >&2
  exit 1
fi
echo "ok — lane-unparked has no grep -q pipeline"
