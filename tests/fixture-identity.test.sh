#!/usr/bin/env bash
# Test for tests/fixture-identity.sh, the one copy of the fixture-repo
# containment guard every identity-writing suite sources (#1144, #1173). Each
# caller only ever takes the pass path, so this suite is what provokes the
# refusal: neutralise the guard and these checks go red, not the callers.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/fixture-identity.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/fixture-identity.XXXXXX")
outside=$(mktemp -d "${TMPDIR:-/tmp}/fixture-identity-outside.XXXXXX")
trap 'rm -rf "$tmp" "$outside"' EXIT
export HOME="$tmp/home"; mkdir -p "$HOME"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
fail=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (want '$2', got '$3')"; fail=1; fi
}

git init -q "$tmp/repo"
fixture_identity "$tmp/repo" "$tmp" 2>"$tmp/err"
check "repo under the root is accepted" 0 $?
check "accepted repo gets the fixture email" t@example.com "$(git -C "$tmp/repo" config user.email)"
check "accepted repo gets the fixture name" t "$(git -C "$tmp/repo" config user.name)"

git init -q "$outside/repo"
fixture_identity "$outside/repo" "$tmp" 2>"$tmp/err"
check "repo outside the root is refused" 1 $?
check "refused repo is left without an email" "" "$(git -C "$outside/repo" config --local user.email)"
grep -q "not under $tmp" "$tmp/err"; check "refusal names the root" 0 $?

# A path that is no repo at all: `git -C` fails, and the guard must read that
# empty answer as a refusal, never fall through to a write in the cwd's repo.
before=$(git -C "$here" config --local user.email)
fixture_identity "$tmp/missing" "$tmp" 2>"$tmp/err"
check "missing repo is refused" 1 $?
check "cwd checkout's email is untouched" "$before" "$(git -C "$here" config --local user.email)"

exit $fail
