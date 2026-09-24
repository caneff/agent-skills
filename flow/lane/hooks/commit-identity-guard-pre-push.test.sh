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
# Name the repo and refuse a target outside our own mktemp dir: a bare
# `git config` after a failed `cd` wrote the real checkout's config (#1144).
case "$(git -C "$repo" rev-parse --show-toplevel)" in
  "$(cd "$tmp" && pwd -P)"/*) ;;
  *) echo "FAIL: fixture repo is not under $tmp" >&2; exit 2 ;;
esac
git -C "$repo" config user.email t@example.com
git -C "$repo" config user.name t
cd "$repo" || exit 2
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

# no configured email: the guard must refuse on that ground specifically —
# not merely because the mismatch check also fires on an empty $configured,
# which would survive deleting the no-configured-email refusal outright.
git -C "$repo" config --unset user.email
git -c user.email=a@b.c commit -q --allow-empty -m none
push main; check "no configured user.email is refused" 1 $?
grep -q "no user.email is configured" "$tmp/out"; check "the no-configured-email refusal names itself" 0 $?
git -C "$repo" config user.email t@example.com

# zero ref updates on stdin: git's own protocol always sends at least one
# when the hook runs at all, so this is either a starved stdin (#1006 S1) or
# a hook invoked some other way — refuse rather than read silence as clean.
: | "$here/commit-identity-guard-pre-push.sh" origin "$remote" >"$tmp/out" 2>&1
check "zero ref updates on stdin is refused" 1 $?
grep -q "no ref updates were read" "$tmp/out"; check "the zero-refs refusal names itself" 0 $?

# a remote registered under a name other than "origin": the new-branch range
# (`rev-list --not --remotes=$1`) must key off the hook's own $1, not a
# hard-coded "origin", or a commit already known to *origin*'s tracking refs
# wrongly excludes it from the check when it is really new to a *different*
# remote (#1006 S3). Reproduced concretely: land a foreign-email commit on
# origin under cover of the override (so it is real, on-disk history, not a
# hook artifact), fetch so a local origin-tracking ref names it, then push
# that same commit as a brand-new branch to a second remote — a
# hard-coded "origin" pattern would match it via the first remote's tracking
# ref and skip it entirely on the second.
env COMMIT_IDENTITY_OVERRIDE="seed" git -c user.email=real@gmail.com commit -q --allow-empty -m shared
seed_sha=$(git rev-parse HEAD)
COMMIT_IDENTITY_OVERRIDE="seed" push shared-origin
git fetch -q origin >/dev/null 2>&1
git reset -q --hard HEAD~1

other_remote="$tmp/other.git"
git init -q --bare "$other_remote"
git remote add other "$other_remote"
git checkout -qb other-feature "$seed_sha"
git push other "HEAD:refs/heads/other-feature" >"$tmp/out" 2>&1
check "a commit already on origin's tracking ref is still checked when pushed new to another remote" 1 $?
git checkout -q main
git branch -qD other-feature

# an existing branch rebased onto a remote trunk that holds a foreign-identity
# commit (GitHub's own squash-merge: author the owner's noreply, committer
# noreply@github.com, #1149). `remote_sha..local_sha` then lists the trunk's
# commit, already on origin, and the guard refused the --force-with-lease push
# of a correctly rebased worker branch. Only commits new to the remote count.
base=$(git rev-parse HEAD)
git checkout -qb work "$base"
git commit -q --allow-empty -m workcommit
push work
git checkout -qb trunk "$base"
GIT_AUTHOR_EMAIL=5097759+someone@users.noreply.github.com GIT_COMMITTER_EMAIL=noreply@github.com \
  COMMIT_IDENTITY_OVERRIDE="fixture: github squash-merge" git commit -q --allow-empty -m squashed
COMMIT_IDENTITY_OVERRIDE="fixture: github squash-merge" push trunk
git fetch -q origin >/dev/null 2>&1
git checkout -q work
git rebase -q origin/trunk >/dev/null 2>&1
git push --force-with-lease origin "HEAD:refs/heads/work" >"$tmp/out" 2>&1
check "a branch rebased onto a remote commit with a foreign committer pushes with lease" 0 $?

# the same push must still refuse a foreign commit replayed locally on top
git -c user.email=real@gmail.com commit -q --allow-empty -m replayedagain
git push --force-with-lease origin "HEAD:refs/heads/work" >"$tmp/out" 2>&1
check "a locally replayed foreign commit on an existing branch is still refused" 1 $?
grep -q "real@gmail.com" "$tmp/out"; check "that refusal names the replayed email" 0 $?
git reset -q --hard HEAD~1
git checkout -q main

exit $fail
