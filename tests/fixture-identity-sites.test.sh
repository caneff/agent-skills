#!/usr/bin/env bash
# Test for #1728: every fixture git identity goes through the one checked
# helper per language (tests/fixture-identity.sh, common/fixture_identity.py,
# flow/lane/tests/support/identity.rs). A `config user.*`, `-c user.*=` or
# GIT_(AUTHOR|COMMITTER)_(NAME|EMAIL) write anywhere else is how `t <t@t>`
# reached a real worker's commit, so it fails here, naming the line. The scan
# runs first on a shadow repo holding one violation, so a scan that matched
# nothing could not pass.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
root=$(git rev-parse --show-toplevel) || exit 1
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (want '$2', got '$3')"; fail=1; fi; }

# Files that may name an identity, each for a stated reason.
allowed=''
allowed+='tests/fixture-identity\.sh|common/fixture_identity\.py|flow/lane/tests/support/identity\.rs'  # the helpers
allowed+='|tests/fixture-identity-sites\.test\.sh'                                                       # this scan's own patterns
allowed+='|tests/fixture-identity\.test\.sh|common/fixture_identity_test\.py|flow/lane/tests/fixture_identity\.rs'  # the helpers' own tests
allowed+='|flow/lane/hooks/commit-identity-guard[^/]*'                                                   # the guard reads and refuses identities
allowed+='|flow/lane/tests/implement_dispatch\.rs'                                                       # runs the guard against a foreign -c identity
allowed+='|tests/identity-snapshot\.test\.sh'                                                            # provokes the config write all.sh must catch
allowed+='|tests/all\.sh'                                                                                # reads the checkout identity
allowed+='|flow/claude/settings\.json|flow/lane/tests/fixtures/body_targets\.json'                       # permission and target text, not git
allowed+='|flow/lane/src/targets\.rs|test-audit/fixtures/test_user_service\.py'                          # prose and a `user.name` attribute
allowed_files=${allowed#|}

pattern='config[^|;&]*user\.(name|email)|"user\.(name|email)"|user\.(name|email)=|GIT_(AUTHOR|COMMITTER)_(NAME|EMAIL)|--author[= ]'

scan() { # <repo root>: tracked, non-Markdown files outside docs/ and the allowlist that name an identity
  git -C "$1" grep -nIE -e "$pattern" -- . ':!*.md' ':!docs/' 2>/dev/null |
    grep -Ev "^($allowed_files):" || true
}

shadow=$(mktemp -d "${TMPDIR:-/tmp}/identity-sites.XXXXXX") || exit 1
trap 'rm -rf "$shadow"' EXIT
git init -q "$shadow"
printf 'git config user.email t@t\n' >"$shadow/leak.sh"
printf 'ok\n' >"$shadow/clean.sh"
printf 'git config --global user.email t@t\n' >"$shadow/global.sh"
printf 'git -C d config --local user.name t\n' >"$shadow/local.sh"
printf 'git config set user.name t\n' >"$shadow/set.sh"
printf 'git commit --author="t <t@t>" -m x\n' >"$shadow/author.sh"
git -C "$shadow" add -A
check "a shadow repo's identity writes are all found, whatever the flags" \
  "author.sh global.sh leak.sh local.sh set.sh" "$(scan "$shadow" | cut -d: -f1 | sort | tr '\n' ' ' | sed 's/ $//')"

found=$(scan "$root")
check "no identity is written outside the helpers" "" "$found"
[ -z "$found" ] || printf '%s\n' "$found" | sed 's/^/  /'
exit $fail
