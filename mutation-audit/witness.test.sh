#!/usr/bin/env bash
# Guards #1331: mutation-audit's single-diff witness mode. One patch and one
# covering test command go in; one outcome line (`red`, `green` or `unknown`)
# and the suite's own message come out, from a throwaway worktree, with the
# reviewed checkout left exactly as found.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool="$here/witness.sh"
[ -f "$tool" ] || { echo "FAIL: missing $tool" >&2; exit 1; }

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'git -C "$scratch/repo" worktree prune 2>/dev/null; rm -rf "$scratch"' EXIT
(
  cd "$scratch" && git init -q -b main repo && cd repo &&
  . "$here/../tests/fixture-identity.sh" && fixture_identity "$scratch/repo" "$scratch" &&
  printf 'def f():\n    return 1\n' >mod.py &&
  printf 'import mod\nassert mod.f() == 1, "MUTANT-mod: mod.f() no longer returns 1"\n' >test_mod.py &&
  git add -A && git commit -qm base &&
  git worktree add -q --detach "$scratch/reviewed" HEAD
) >/dev/null 2>&1 || { echo "FAIL: could not build the fixture repo" >&2; exit 1; }
repo="$scratch/reviewed"

# Patches made with `git diff` in the fixture itself, then reverted, so each
# applies at the fixture's HEAD exactly as a reviewer's would.
make_patch() { # <name> <sed expression on mod.py>
  sed -i "$2" "$repo/mod.py" &&
    git -C "$repo" diff >"$scratch/$1.patch" &&
    git -C "$repo" checkout -q -- mod.py
  [ -s "$scratch/$1.patch" ] || { echo "FAIL: could not build patch $1" >&2; exit 1; }
}
make_patch breaks 's/return 1/return 2/'
make_patch inert 's/return 1/return 1  # same value/'
printf -- '--- a/absent.py\n+++ b/absent.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n' >"$scratch/stale.patch"

fail=0
run() { # <out-name> <args...>: runs the tool from inside the reviewed tree
  local name="$1"; shift
  ( cd "$repo" && bash "$tool" "$@" ) >"$scratch/$name.out" 2>&1
  printf '%s\n' "$?" >"$scratch/$name.rc"
}
expect() { # <out-name> <outcome>
  if ! grep -qx "outcome: $2" "$scratch/$1.out"; then
    echo "FAIL: $1 did not report 'outcome: $2'" >&2; cat "$scratch/$1.out" >&2; fail=1
  fi
  [ "$(cat "$scratch/$1.rc")" = 0 ] ||
    { echo "FAIL: $1 exited $(cat "$scratch/$1.rc"), not 0" >&2; fail=1; }
}

# A patch that breaks the asserted behaviour: red, with the suite's own message.
run red --patch "$scratch/breaks.patch" --test 'python3 test_mod.py' --no-ledger
expect red red
grep -q 'MUTANT-mod' "$scratch/red.out" ||
  { echo "FAIL: the red outcome did not carry the assertion's own message" >&2; cat "$scratch/red.out" >&2; fail=1; }

# A patch the test cannot see: green, the hollow-witness answer.
run green --patch "$scratch/inert.patch" --test 'python3 test_mod.py' --no-ledger
expect green green

# A patch that does not apply never reached the suite: unknown, never red,
# though the run that tried it exited non-zero (defect class 1).
run stale --patch "$scratch/stale.patch" --test 'python3 test_mod.py' --no-ledger
expect stale unknown

# A covering command that does not exist never ran: unknown, not a red whose
# message is "command not found".
run noexec --patch "$scratch/breaks.patch" --test '/nonexistent/covering-suite' --no-ledger
expect noexec unknown

# The reviewed tree is untouched by every run above.
[ "$(cat "$repo/mod.py")" = "$(printf 'def f():\n    return 1')" ] ||
  { echo "FAIL: a witness run wrote its patch into the reviewed tree" >&2; fail=1; }
[ -z "$(git -C "$repo" status --porcelain)" ] ||
  { echo "FAIL: a witness run left the reviewed tree dirty" >&2; git -C "$repo" status --porcelain >&2; fail=1; }
[ "$(git -C "$repo" worktree list | wc -l)" -eq 2 ] ||
  { echo "FAIL: a witness run left a throwaway worktree registered" >&2; git -C "$repo" worktree list >&2; fail=1; }

# Inside a review it writes the same ledger row the witness check does, typed
# call-site-mutation when asked.
run ledger --patch "$scratch/breaks.patch" --test 'python3 test_mod.py' --id cs-mod --call-site \
  --repo skills --ticket 1 --round 1 --ledger "$scratch/ledger.jsonl"
expect ledger red
row="$(python3 -c '
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
print(" ".join(":".join(str(r.get(k)) for k in ("mutation_id", "type", "outcome")) for r in rows))
' "$scratch/ledger.jsonl" 2>&1)"
[ "$row" = 'cs-mod:call-site-mutation:red' ] ||
  { echo "FAIL: the ledger holds '$row', wanted one cs-mod call-site-mutation red row" >&2; fail=1; }

# No ledger arguments and no --no-ledger is refused, not a run that silently
# drops its cost row.
run noledger --patch "$scratch/breaks.patch" --test 'python3 test_mod.py'
[ "$(cat "$scratch/noledger.rc")" = 2 ] ||
  { echo "FAIL: a run with no ledger arguments exited $(cat "$scratch/noledger.rc"), not 2" >&2; cat "$scratch/noledger.out" >&2; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "PASS mutation-audit/witness.test.sh"
else
  exit 1
fi
