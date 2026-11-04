#!/bin/sh
# lane commit-identity pre-push guard (#1006). Installed as
# hooks/commit-identity-guard-pre-push by implement-dispatch, which also
# makes pre-push call it. The pre-commit guard (#934,
# commit-identity-guard.sh) only fires on `git commit`, so a rebase,
# cherry-pick, or other replay can rewrite a commit's author or committer
# email without ever going through `git commit` — and the lane rebases onto
# the default branch before every push. This hook re-checks every commit
# about to be pushed, so a rewritten email is refused here, at the checkout,
# instead of at GitHub's email-privacy edge (#909).
# Legitimate other identity: COMMIT_IDENTITY_OVERRIDE="<why>" git push ...
# (the reason is required and is printed).
# The configured value is read with `-c` overrides stripped, since those are
# exactly what this guards against.
# Checks both AUTHOR and COMMITTER email against the checkout's configured
# identity, on every commit in the pushed range — including one this
# checkout never authored, such an imported commit or one with a distinct
# original author. That refusal is correct for the lane (a rebase or
# cherry-pick from another identity is exactly what this guards against),
# but is a real, expected refusal on an imported/co-authored commit whose
# author email isn't the checkout's own; use COMMIT_IDENTITY_OVERRIDE there.

if [ -n "${COMMIT_IDENTITY_OVERRIDE:-}" ]; then
  echo "commit-identity guard (pre-push): override in effect — $COMMIT_IDENTITY_OVERRIDE" >&2
  exit 0
fi

configured=$(env -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT git config user.email)
if [ -z "$configured" ]; then
  echo "commit-identity guard (pre-push): refused — no user.email is configured for this checkout; set it in the repo config (git config user.email <addr>) before pushing." >&2
  exit 1
fi

zero=0000000000000000000000000000000000000000
remote_name=${1:-origin}
bad=0
saw_a_ref=0
while read -r local_ref local_sha remote_ref remote_sha; do
  saw_a_ref=1
  [ -z "${local_sha:-}" ] && continue
  [ "$local_sha" = "$zero" ] && continue  # deleting a ref: nothing is being pushed
  # A new branch has no remote sha to exclude; an existing one excludes it.
  # Either way skip what any remote ref already holds, not just $remote_sha:
  # a rebase onto the default branch pulls in GitHub's own squash-merge
  # commits (committer noreply@github.com), already on origin and not ours to
  # re-check (#1149). Do not simplify this back to $remote_sha..$local_sha.
  exclude=
  [ -n "${remote_sha:-}" ] && [ "$remote_sha" != "$zero" ] && exclude=$remote_sha
  # $exclude unquoted: empty must vanish, not become an empty revision.
  range=$(git rev-list "$local_sha" --not $exclude --remotes="$remote_name") || {
    echo "commit-identity guard (pre-push): refused — could not enumerate the commits $local_ref is pushing (git rev-list $local_sha --not $exclude --remotes=$remote_name failed); refusing rather than reading that as nothing to check." >&2
    bad=1
    continue
  }
  for sha in $range; do
    author_email=$(git log -1 --format=%ae "$sha") || {
      echo "commit-identity guard (pre-push): refused — could not read $sha's author email; refusing rather than reading that as a match." >&2
      bad=1
      continue
    }
    committer_email=$(git log -1 --format=%ce "$sha") || {
      echo "commit-identity guard (pre-push): refused — could not read $sha's committer email; refusing rather than reading that as a match." >&2
      bad=1
      continue
    }
    for pair in "AUTHOR $author_email" "COMMITTER $committer_email"; do
      role=${pair%% *}; email=${pair#* }
      if [ "$email" != "$configured" ]; then
        echo "commit-identity guard (pre-push): refused — $sha's $role email is '$email' but this checkout's configured user.email is '$configured'. This commit was likely replayed by a rebase or cherry-pick under a different identity; identity comes from the checkout, never from session context. A legitimate other identity: COMMIT_IDENTITY_OVERRIDE=\"<why>\" git push ..." >&2
        bad=1
      fi
    done
  done
done
if [ "$saw_a_ref" -eq 0 ]; then
  # git lists only refs it will send: it leaves out a ref already equal to the
  # remote's and one it is about to reject as non-fast-forward (#1618). An
  # empty list is therefore a push with nothing to check, and a stale or
  # diverged branch is reported by git itself ("rejected ... fetch first" /
  # "non-fast-forward"). The hook is given no refspec, so it cannot name the
  # branch; git's own message does. A starved stdin is closed one layer up:
  # the lane's wrapper fails the push when it cannot buffer the list (#1006).
  echo "commit-identity guard (pre-push): no ref updates on stdin — nothing to push, nothing to check (the branch is already up to date, or git will reject it itself as non-fast-forward)." >&2
fi
exit $bad
