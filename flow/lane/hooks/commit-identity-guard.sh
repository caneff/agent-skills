#!/bin/sh
# lane commit-identity guard (#934). Installed as hooks/commit-identity-guard by
# implement-dispatch, which also makes pre-commit call it. Refuses a commit
# whose author or committer email is not the checkout's configured user.email, so the failure lands at commit time
# with the work still uncommitted, not at GitHub's email-privacy block after.
# Legitimate other identity: COMMIT_IDENTITY_OVERRIDE="<why>" git commit ...
# (the reason is required and is printed).
# The configured value is read with `-c` overrides stripped, since those are
# exactly what this guards against.

if [ -n "${COMMIT_IDENTITY_OVERRIDE:-}" ]; then
  echo "commit-identity guard: override in effect — $COMMIT_IDENTITY_OVERRIDE" >&2
  exit 0
fi

configured=$(env -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT git config user.email)
if [ -z "$configured" ]; then
  echo "commit-identity guard: refused — no user.email is configured for this checkout; set it in the repo config (git config user.email <addr>) before committing." >&2
  exit 1
fi

bad=0
for role in AUTHOR COMMITTER; do
  ident=$(git var "GIT_${role}_IDENT") || exit 1
  email=${ident#*<}; email=${email%%>*}
  if [ "$email" != "$configured" ]; then
    echo "commit-identity guard: refused — $role email is '$email' but this checkout's configured user.email is '$configured'. Drop the -c user.email / GIT_${role}_EMAIL / --author override; identity comes from the checkout, never from session context. A legitimate other identity: COMMIT_IDENTITY_OVERRIDE=\"<why>\" git commit ..." >&2
    bad=1
  fi
done
exit $bad
