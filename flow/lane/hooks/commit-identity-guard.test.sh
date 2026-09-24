#!/usr/bin/env bash
# Test for the commit-identity guard (#934): a commit whose author or
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
# Name the repo and refuse a target outside our own mktemp dir: a bare
# `git config` after a failed `cd` wrote the real checkout's config (#1144).
case "$(git -C "$repo" rev-parse --show-toplevel)" in
  "$(cd "$tmp" && pwd -P)"/*) ;;
  *) echo "FAIL: fixture repo is not under $tmp" >&2; exit 2 ;;
esac
git -C "$repo" config user.email t@example.com
git -C "$repo" config user.name t
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
grep -q "real@gmail.com" "$tmp/out" && grep -q "t@example.com" "$tmp/out"
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

exit $fail
