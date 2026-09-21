#!/usr/bin/env bash
# Guards #909: a worker's commit identity comes from the repo's config, and a
# file whose contents become public (a --body-file) lives in the worker's own
# workspace. Both rules sit in implement/SKILL.md § The brief. A prose
# assertion, not a behavioral test — there is no harness that runs the skill's
# own prose. (The #963 trailer is guarded in pr-up-report-shape.test.sh, the
# #951 --background wording in codex-pass-schedule.test.sh.)
# Resolving via BASH_SOURCE sidesteps a caller's leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

# Both range addresses must exist, or sed widens the range to EOF and every
# check below reads "somewhere in SKILL.md".
for heading in '^## The brief$' '^## Control$'; do
  grep -q "$heading" "$skill" || { echo "FAIL: implement/SKILL.md has no heading matching $heading" >&2; exit 1; }
done
section="$(sed -n '/^## The brief$/,/^## Control$/p' "$skill" | tr '\n' ' ' | tr -s ' ')"
[ -n "$section" ] || { echo "FAIL: could not extract § The brief" >&2; exit 1; }

fail=0
check() {
  case "$section" in
    *"$1"*) ;;
    *) echo "FAIL: implement/SKILL.md § The brief is missing: $1" >&2; fail=1 ;;
  esac
}

check 'Commit identity comes from the repo'"'"'s config.'
check 'Never pass `-c user.email` or `-c user.name` to `git commit`'
check 'GitHub'"'"'s email-privacy rule rejected every push'
check 'A file whose contents become public lives under your own workspace'"'"'s `.scratch/`'
check 'every `--body-file` for `gh pr create` and `gh pr edit`'
check 'never `/tmp`, never a shared scratchpad path'
check 'PR 908 went up carrying #886'"'"'s body'
check 'Your "PR up" message ends with the controller trailer'

if [ "$fail" -eq 0 ]; then echo "PASS implement/worker-hygiene-wording.test.sh"; else exit 1; fi
