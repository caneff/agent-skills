#!/usr/bin/env bash
# Test for the commit-identity guard: a commit whose author or
# committer email is not the checkout's configured user.email is refused at
# commit time. Runs the real hook under real `git commit` in a scratch repo.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
hook="$here/commit-identity-guard.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/identity-guard.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
fail=0
check() { # name expected-exit actual-exit
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (want exit $2, got $3)"; fail=1; fi
}

export HOME="$tmp/home"; mkdir -p "$HOME"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
unset GIT_AUTHOR_EMAIL GIT_COMMITTER_EMAIL COMMIT_IDENTITY_OVERRIDE
repo="$tmp/repo"
git init -q "$repo"
. "$here/../../../tests/fixture-identity.sh"
fixture_identity "$repo" "$tmp" || exit 2
# the guard refuses a fixture identity, so the guarded identity is a non-fixture one
git -C "$repo" config user.email me@corp.dev
git -C "$repo" config user.name Me
cd "$repo" || exit 2
cp "$hook" .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

n=0
try() { # args to git commit; prints nothing, returns exit
  n=$((n + 1)); echo "$n" >f; git add f
  "$@" >"$tmp/out" 2>&1
}

try git commit -qm plain;                                    check "configured identity passes" 0 $?
try git -c user.email=real@gmail.com commit -qm dashc;       check "-c user.email is refused" 1 $?
grep -q "real@gmail.com" "$tmp/out" && grep -q "me@corp.dev" "$tmp/out"
check "refusal names both emails" 0 $?
try env GIT_AUTHOR_EMAIL=real@gmail.com git commit -qm auth; check "author env is refused" 1 $?
try env GIT_COMMITTER_EMAIL=real@gmail.com git commit -qm comm; check "committer env is refused" 1 $?
try git commit -qm x --author="A <real@gmail.com>";          check "--author is refused" 1 $?
try env COMMIT_IDENTITY_OVERRIDE="release bot" git -c user.email=bot@x.org commit -qm ov
check "override with a reason passes" 0 $?
grep -q "release bot" "$tmp/out"; check "override names its reason" 0 $?
try env COMMIT_IDENTITY_OVERRIDE= git -c user.email=bot@x.org commit -qm empty
check "empty override is not an override" 1 $?

# no configured email: the guard must refuse, not read absence as a match
git -C "$repo" config --unset user.email
try env GIT_AUTHOR_EMAIL=a@b.c GIT_COMMITTER_EMAIL=a@b.c git commit -qm none
check "no configured user.email is refused" 1 $?

# author or committer NAME differing from the configured user.name is refused
git -C "$repo" config user.email me@corp.dev
try env GIT_AUTHOR_NAME=Mallory git commit -qm aname;         check "author name env is refused" 1 $?
grep -q "Mallory" "$tmp/out" && grep -q "'Me'" "$tmp/out"; check "name refusal names both names" 0 $?
try env GIT_COMMITTER_NAME=Mallory git commit -qm cname;      check "committer name env is refused" 1 $?

# a fixture identity configured on a checkout outside every temp root is
# refused (#1728): comparing to the configured value alone passes a polluted
# config. Suites build fixtures under a temp root and run the real hooks there,
# so a fixture identity inside one passes. /dev/shm is outside every temp root,
# so a repo there reads as a real checkout.
shm=$(mktemp -d /dev/shm/identity-guard.XXXXXX) || exit 2
trap 'rm -rf "$tmp" "$shm"' EXIT
git init -q "$shm/real"
cp "$hook" "$shm/real/.git/hooks/pre-commit"
chmod +x "$shm/real/.git/hooks/pre-commit"
cd "$shm/real" || exit 2
for fx in t@t t@example.invalid t@example.test; do
  git config user.email "$fx"; git config user.name Me
  try git commit -qm fx;                                      check "configured fixture $fx is refused outside the temp roots" 1 $?
  grep -q "fixture" "$tmp/out"; check "fixture refusal says fixture ($fx)" 0 $?
  git -C "$repo" config user.email "$fx"
  ( cd "$repo" && n=$((n + 1)) && echo "$n" >f && git add f && git commit -qm fxok >"$tmp/out" 2>&1 )
  check "configured fixture $fx passes inside a temp root" 0 $?
done
git config user.email me@corp.dev; git config user.name t
try git commit -qm fxname;                                    check "configured fixture name t is refused outside the temp roots" 1 $?
git config user.name Me
try git commit -qm real;                                      check "a real configured identity passes outside the temp roots" 0 $?

exit $fail
