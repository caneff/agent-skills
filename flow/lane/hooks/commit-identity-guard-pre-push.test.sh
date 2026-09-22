#!/usr/bin/env bash
# Test for the commit-identity pre-push guard (#1006): the pre-commit guard
# (#934) only fires on `git commit`, so a rebase or cherry-pick that replays
# a commit under a different identity slips past it entirely and is only
# caught at GitHub's email-privacy edge (#909) — after the lane's mandated
# rebase-then-push. This hook re-checks every commit about to be pushed.
# Runs the real hook under a real `git push` to a local bare remote.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
hook="$here/commit-identity-guard-pre-push.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/identity-guard-push.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
fail=0
check() { # name expected-exit actual-exit
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (want exit $2, got $3)"; fail=1; fi
}

export HOME="$tmp/home"; mkdir -p "$HOME"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
unset GIT_AUTHOR_EMAIL GIT_COMMITTER_EMAIL COMMIT_IDENTITY_OVERRIDE

remote="$tmp/remote.git"
git init -q --bare "$remote"

repo="$tmp/repo"
git init -q "$repo"
cd "$repo" || exit 2
git config user.email t@example.com
git config user.name t
git remote add origin "$remote"
mkdir -p .git/hooks
cp "$hook" .git/hooks/pre-push
chmod +x .git/hooks/pre-push

push() { # branch
  git push origin "HEAD:refs/heads/$1" >"$tmp/out" 2>&1
}

echo one >f; git add f; git commit -qm one
push main; check "configured identity pushes" 0 $?

# a replayed commit (simulating a rebase run with a foreign -c user.email,
# as #909/#1006 describes) landing on top, still under the configured branch
git -c user.email=real@gmail.com commit -q --allow-empty -m replayed
push main; check "a replayed foreign-email commit is refused" 1 $?
grep -q "real@gmail.com" "$tmp/out" && grep -q "t@example.com" "$tmp/out"
check "refusal names both emails" 0 $?

# fix it and retry
git commit -q --allow-empty --amend --reset-author -m replayed
push main; check "amended back to the configured identity pushes" 0 $?

# a brand-new branch (remote side has no ref yet) with a foreign-email commit
git checkout -qb feature
git -c user.email=real@gmail.com commit -q --allow-empty -m featurework
push feature; check "a foreign-email commit on a brand-new branch is refused" 1 $?
git checkout -q main
git branch -qD feature

# the override escape
env COMMIT_IDENTITY_OVERRIDE="release bot" git -c user.email=bot@x.org commit -q --allow-empty -m ov
COMMIT_IDENTITY_OVERRIDE="release bot" push main
check "override with a reason passes" 0 $?
grep -q "release bot" "$tmp/out"; check "override names its reason" 0 $?
git -c user.email=real@gmail.com commit -q --allow-empty -m unoverridden
COMMIT_IDENTITY_OVERRIDE= push main
check "empty override is not an override" 1 $?
git reset -q --hard HEAD~1

# no configured email: the guard must refuse, not read absence as a match
git config --unset user.email
git -c user.email=a@b.c commit -q --allow-empty -m none
push main; check "no configured user.email is refused" 1 $?

exit $fail
