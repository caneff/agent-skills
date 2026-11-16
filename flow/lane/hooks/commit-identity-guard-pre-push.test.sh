#!/usr/bin/env bash
# Test for the commit-identity pre-push guard: the pre-commit guard only
# fires on `git commit`, so a rebase or cherry-pick that replays a commit
# under a different identity slips past it entirely and is only caught at
# GitHub's email-privacy edge — after the lane's mandated rebase-then-push.
# This hook re-checks every commit about to be pushed. Runs the real hook
# under a real `git push` to a local bare remote.
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
. "$here/../../../tests/fixture-identity.sh"
fixture_identity "$repo" "$tmp" || exit 2
# the guard refuses a fixture identity, so the guarded identity is a non-fixture one
git -C "$repo" config user.email me@corp.dev
git -C "$repo" config user.name Me
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

# a replayed commit (simulating a rebase run with a foreign -c user.email)
# landing on top, still under the configured branch
git -c user.email=real@gmail.com commit -q --allow-empty -m replayed
push main; check "a replayed foreign-email commit is refused" 1 $?
grep -q "real@gmail.com" "$tmp/out" && grep -q "me@corp.dev" "$tmp/out"
check "refusal names both emails" 0 $?

git commit -q --allow-empty --amend --reset-author -m replayed
push main; check "amended back to the configured identity pushes" 0 $?

git checkout -qb feature
git -c user.email=real@gmail.com commit -q --allow-empty -m featurework
push feature; check "a foreign-email commit on a brand-new branch is refused" 1 $?
git checkout -q main
git branch -qD feature

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
git -C "$repo" config user.email me@corp.dev

# zero ref updates on stdin: the guard passes an empty push and says why
# (rationale: the hook's own comment), rather than failing the lane step.
: | "$here/commit-identity-guard-pre-push.sh" origin "$remote" >"$tmp/out" 2>&1
check "zero ref updates on stdin passes" 0 $?
grep -q "nothing to push" "$tmp/out"; check "the empty-push pass names itself" 0 $?

# earlier cases left an unpushed foreign-email commit on main: put main back
# on what the remote holds so the next push really is up to date.
git fetch -q origin && git reset -q --hard origin/main
check "fixture: main equals the remote's" 0 $?

# the same through a real `git push`: the hook must run (its note is in the
# output) and the push must succeed. Guards against a pass that only works
# because git never called the hook.
git push origin HEAD:refs/heads/main >"$tmp/out" 2>&1
check "a real up-to-date push passes" 0 $?
grep -q "nothing to push" "$tmp/out"; check "the real up-to-date push ran the hook" 0 $?
grep -q "refused" "$tmp/out"; check "the real up-to-date push is not refused" 1 $?

# a diverged branch: the remote holds a commit this checkout lacks. Git, not
# the guard, rejects it, and the output names the real cause.
git checkout -qb stale
git commit -q --allow-empty -m staleonly
git push origin HEAD:refs/heads/stale-base >"$tmp/out" 2>&1
check "fixture: stale-base reaches the remote" 0 $?
git reset -q --hard HEAD~1
git commit -q --allow-empty -m diverged
git push origin HEAD:refs/heads/stale-base >"$tmp/out" 2>&1
check "a non-fast-forward push fails" 1 $?
grep -qi "non-fast-forward\|fetch first" "$tmp/out"; check "the failure names the non-fast-forward, git's own reason" 0 $?
grep -q "commit-identity guard (pre-push): refused" "$tmp/out"; check "the identity guard is not the one refusing a non-fast-forward" 1 $?

# The remote's new commit was made in another clone and never fetched here:
# git lists the ref, so the guard cannot read the remote sha. It must refuse
# and say the branch is behind or diverged, not leak a rev-list "bad object".
other_clone="$tmp/other-clone"
git clone -q "$remote" "$other_clone" >/dev/null 2>&1
( cd "$other_clone" && git checkout -q stale-base && git -c user.name=o -c user.email=o@example.com commit -q --allow-empty -m elsewhere \
  && COMMIT_IDENTITY_OVERRIDE="fixture: another clone" git push -q origin HEAD:refs/heads/stale-base ) >/dev/null 2>&1
check "fixture: another clone advanced stale-base" 0 $?
git push origin HEAD:refs/heads/stale-base >"$tmp/out" 2>&1
check "an unfetched stale branch is refused" 1 $?
grep -q "fetch" "$tmp/out" && grep -q "stale-base" "$tmp/out"; check "the refusal names the branch and says to fetch" 0 $?
grep -q "bad object\|could not enumerate" "$tmp/out"; check "the refusal is not a rev-list failure" 1 $?
git checkout -q main
git branch -qD stale

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

# An existing branch rebased onto a remote trunk holding a foreign-identity
# commit (GitHub squash-merge: noreply committer). `remote_sha..local_sha`
# lists the trunk's commit, already on origin, and refused a correct
# --force-with-lease push. Only commits new to the remote count.
base=$(git rev-parse HEAD)
git checkout -qb work "$base"
git commit -q --allow-empty -m workcommit
push work; check "fixture: the work branch reaches the remote" 0 $?
git checkout -qb trunk "$base"
GIT_AUTHOR_EMAIL=5097759+someone@users.noreply.github.com GIT_COMMITTER_EMAIL=noreply@github.com \
  COMMIT_IDENTITY_OVERRIDE="fixture: github squash-merge" git commit -q --allow-empty -m squashed
COMMIT_IDENTITY_OVERRIDE="fixture: github squash-merge" push trunk
check "fixture: the trunk commit reaches the remote" 0 $?
git fetch -q origin >/dev/null 2>&1
check "fixture: origin/trunk is fetched" 0 $?
git checkout -q work
git rebase -q origin/trunk >/dev/null 2>&1
check "fixture: the work branch rebases onto origin/trunk" 0 $?
git push --force-with-lease origin "HEAD:refs/heads/work" >"$tmp/out" 2>&1
check "a branch rebased onto a remote commit with a foreign committer pushes with lease" 0 $?

git -c user.email=real@gmail.com commit -q --allow-empty -m replayedagain
git push --force-with-lease origin "HEAD:refs/heads/work" >"$tmp/out" 2>&1
check "a locally replayed foreign commit on an existing branch is still refused" 1 $?
grep -q "real@gmail.com" "$tmp/out"; check "that refusal names the replayed email" 0 $?
git reset -q --hard HEAD~1
git checkout -q main

# a fixture identity configured on a checkout outside every temp root is
# refused at push (#1728); inside one it passes. /dev/shm is outside every temp
# root, so a repo there reads as a real checkout.
git -C "$repo" config user.email t@t
git commit -q --allow-empty -m fixturecommit
push main; check "a configured fixture identity pushes inside a temp root" 0 $?
git -C "$repo" config user.email me@corp.dev
git reset -q --hard HEAD~1
shm=$(mktemp -d /dev/shm/identity-guard-push.XXXXXX) || exit 2
trap 'rm -rf "$tmp" "$shm"' EXIT
git init -q --bare "$shm/remote.git"
git init -q "$shm/real"
cp "$hook" "$shm/real/.git/hooks/pre-push"
chmod +x "$shm/real/.git/hooks/pre-push"
cd "$shm/real" || exit 2
git remote add origin "$shm/remote.git"
git config user.email t@t; git config user.name t
git commit -q --allow-empty -m fx
push main; check "a configured fixture identity is refused at push outside the temp roots" 1 $?
grep -q "fixture" "$tmp/out"; check "the fixture refusal says fixture" 0 $?
git config user.email me@corp.dev; git config user.name Me
git commit -q --allow-empty --amend --reset-author -m real
push main; check "a real configured identity pushes outside the temp roots" 0 $?

exit $fail
