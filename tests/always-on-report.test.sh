#!/usr/bin/env bash
# `tests/all.sh` prints the always-on word count on every run and never fails
# the run on it (#2016): the count includes files outside this repo (the
# vault's Memory/RULES.md), so an overrun nobody here committed must not turn
# the seam red. Runs the real tests/all.sh in a shadow repo holding one passing
# suite, the real checker and a CLAUDE.md padded past the budget.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset TESTS_JOBS TESTS_CPU_BUDGET
root=$(git rev-parse --show-toplevel) || exit 1
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
fail=0
check() { if [ "$2" = 0 ]; then echo "ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

mkdir -p "$shadow/repo/tests" "$shadow/repo/a" "$shadow/repo/flow/claude"
cp "$root/tests/all.sh" "$root/tests/suite-edges.py" "$root/tests/check-always-on.py" "$shadow/repo/tests/"
printf '#!/usr/bin/env bash\nexit 0\n' >"$shadow/repo/a/a.test.sh"
budget=$(sed -n 's/^BUDGET = \([0-9]*\).*/\1/p' "$root/tests/check-always-on.py")
words=$((budget + 5))
yes word | head -n "$words" | tr '\n' ' ' >"$shadow/repo/flow/claude/CLAUDE.md"
git -C "$shadow/repo" init -q
. "$root/tests/fixture-identity.sh"
fixture_identity "$shadow/repo" "$shadow" || exit 2
git -C "$shadow/repo" add -A && git -C "$shadow/repo" commit -qm base
base=$(git -C "$shadow/repo" rev-parse HEAD)

out=$(cd "$shadow/repo" && TESTS_RUN_DIR=off bash tests/all.sh 2>&1); rc=$?
check "an over-budget CLAUDE.md does not fail the full seam" "$([ "$rc" = 0 ]; echo $?)"
check "...and the run names the count and the budget" "$(grep -qxF "always-on: total $words words, over its budget of $budget" <<<"$out"; echo $?)"

echo x >>"$shadow/repo/a/x.txt"; git -C "$shadow/repo" add -A; git -C "$shadow/repo" commit -qm change
out=$(cd "$shadow/repo" && TESTS_RUN_DIR=off bash tests/all.sh --changed "$base" 2>&1); rc=$?
check "a narrowed run prints it too, and passes" "$([ "$rc" = 0 ] && grep -qxF "always-on: total $words words, over its budget of $budget" <<<"$out"; echo $?)"

# The count line must never carry a FAIL line, even with a dead pointer in the file (the
# nightly backstop reads a column-0 FAIL as a failed suite): the seam stays green.
printf 'Before you land: read `~/.agents/skills/flow/claude/NOPE.md`.\n' >>"$shadow/repo/flow/claude/CLAUDE.md"
git -C "$shadow/repo" commit -qam pointer
out=$(cd "$shadow/repo" && TESTS_RUN_DIR=off bash tests/all.sh 2>&1); rc=$?
check "a dead pointer in the file leaves the run green with no FAIL line" "$([ "$rc" = 0 ] && ! grep -q '^FAIL' <<<"$out" && ! grep -q 'not counted' <<<"$out"; echo $?)"

exit "$fail"
