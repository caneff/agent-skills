#!/bin/sh
# lane commit-identity guard. Installed as hooks/commit-identity-guard by
# implement-dispatch, which also makes pre-commit call it. Refuses a commit
# whose author or committer email is not the checkout's configured
# user.email, so the failure lands at commit time with the work still
# uncommitted, not at GitHub's email-privacy block after.
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

# A fixture identity (t@t, t@example.*, name t) configured on a real checkout
# matches itself, so the comparison below would pass it. Suites build their
# fixtures under a temp root and run the real hooks there, so only a checkout
# outside every temp root (${TMPDIR:-/tmp}, /tmp, /var/tmp) is refused (#1728).
configured_name=$(env -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT git config user.name)
if [ -z "$configured_name" ]; then
  echo "commit-identity guard: refused — no user.name is configured for this checkout; set it in the repo config (git config user.name <name>) before committing." >&2
  exit 1
fi
# The name git puts on a commit is the configured one stripped of surrounding
# whitespace and quotes, so compare against that, not the raw value.
ident_name=$(env -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT -u GIT_AUTHOR_NAME -u GIT_COMMITTER_NAME git var GIT_AUTHOR_IDENT) || exit 1
ident_name=${ident_name%% <*}
fixture=
case "$configured" in t@t|t@example.*) fixture="user.email '$configured'" ;; esac
[ "$configured_name" = t ] && fixture="${fixture:+$fixture and }user.name 't'"
if [ -n "$fixture" ]; then
  top=$(cd "$(git rev-parse --show-toplevel)" && pwd -P)
  # An unresolvable root is skipped, never a match: "/*" admits any path.
  inside=
  for root in "${TMPDIR:-/tmp}" /tmp /var/tmp; do
    r=$(cd "$root" 2>/dev/null && pwd -P) || continue
    case "$top" in "$r"/*) inside=1 ;; esac
  done
  case "$inside" in
    1) ;;
    *)
      echo "commit-identity guard: refused — this checkout's configured $fixture looks like a test-fixture identity on a checkout outside every temp root ($top), where a suite may have written it. Restore the real identity (git config user.email <addr>; git config user.name <name>) and rerun the commit. A legitimate other identity: COMMIT_IDENTITY_OVERRIDE=\"<why>\" git commit ..." >&2
      exit 1 ;;
  esac
fi

bad=0
for role in AUTHOR COMMITTER; do
  ident=$(git var "GIT_${role}_IDENT") || exit 1
  email=${ident#*<}; email=${email%%>*}
  if [ "$email" != "$configured" ]; then
    echo "commit-identity guard: refused — $role email is '$email' but this checkout's configured user.email is '$configured'. Drop the -c user.email / GIT_${role}_EMAIL / --author override; identity comes from the checkout, never from session context. A legitimate other identity: COMMIT_IDENTITY_OVERRIDE=\"<why>\" git commit ..." >&2
    bad=1
  fi
  name=${ident%% <*}
  if [ "$name" != "$ident_name" ]; then
    echo "commit-identity guard: refused — $role name is '$name' but this checkout's configured user.name is '$ident_name'. Drop the -c user.name / GIT_${role}_NAME / --author override. A legitimate other identity: COMMIT_IDENTITY_OVERRIDE=\"<why>\" git commit ..." >&2
    bad=1
  fi
done
exit $bad
