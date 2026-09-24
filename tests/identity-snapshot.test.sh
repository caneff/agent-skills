#!/usr/bin/env bash
# Test for #1144: a suite that rewrites the real checkout's user.email or
# user.name (a fixture identity written with a bare `git config` after a
# failed `cd`) must fail tests/all.sh, naming that suite. A clean suite must
# not. Runs the real tests/all.sh in a shadow repo holding only that script
# and a fake suite, so nothing here touches this checkout's config.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root=$(git rev-parse --show-toplevel) || exit 1
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
fail=0
check() { # name expected-exit actual-exit
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "  FAIL $1 (want exit $2, got $3)"; fail=1; fi
}

# The fake suite's body is the argument; the shadow is reset per case.
run_case() { # <suite body> [unset-first]; leaves the run's output in $out, status in $rc
  rm -rf "$shadow/repo"; mkdir -p "$shadow/repo/tests"
  cp "$root/tests/all.sh" "$shadow/repo/tests/all.sh"
  printf '#!/usr/bin/env bash\n%s\n' "$1" >"$shadow/repo/fake.test.sh"
  git -C "$shadow/repo" init -q
  git -C "$shadow/repo" config user.email owner@example.org
  git -C "$shadow/repo" config user.name owner
  # A second argument starts the case with user.email unset, so a suite that
  # sets it to empty is a change only the `<unset>` marker can see.
  [ -n "${2-}" ] && git -C "$shadow/repo" config --unset user.email
  git -C "$shadow/repo" add -A
  git -C "$shadow/repo" -c user.email=t@example.com -c user.name=t commit -qm shadow
  out=$(cd "$shadow/repo" && bash tests/all.sh 2>&1); rc=$?
}

run_case 'exit 0'
check "a suite that leaves the identity alone passes" 0 $rc

run_case 'git config user.email t@example.com'
check "a suite that rewrites user.email fails the gate" 1 $rc
printf '%s\n' "$out" | grep -q 'fake.test.sh' && printf '%s\n' "$out" | grep -q 'user.email'
check "the failure names the suite and the key" 0 $?

run_case 'git config user.name t'
check "a suite that rewrites user.name fails the gate" 1 $rc

run_case 'git config --unset user.email'
check "a suite that unsets user.email fails the gate" 1 $rc

run_case 'git config user.email ""' unset-first
check "a suite that sets an unset user.email to empty fails the gate" 1 $rc

exit $fail
