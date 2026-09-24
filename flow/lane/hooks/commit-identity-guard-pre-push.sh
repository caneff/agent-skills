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
  if [ -z "${remote_sha:-}" ] || [ "$remote_sha" = "$zero" ]; then
    range=$(git rev-list "$local_sha" --not --remotes="$remote_name") || {
      echo "commit-identity guard (pre-push): refused — could not enumerate the commits $local_ref is pushing (git rev-list failed); refusing rather than reading that as nothing to check." >&2
      bad=1
      continue
    }
  else
    range=$(git rev-list "$local_sha" --not "$remote_sha" --remotes="$remote_name") || {
      echo "commit-identity guard (pre-push): refused — could not enumerate the commits $local_ref is pushing between $remote_sha and $local_sha (git rev-list failed); refusing rather than reading that as nothing to check." >&2
      bad=1
      continue
    }
  fi
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
  echo "commit-identity guard (pre-push): refused — no ref updates were read on stdin; git's pre-push protocol always sends at least one, so refusing rather than reading silence as nothing to check." >&2
  bad=1
fi
exit $bad
