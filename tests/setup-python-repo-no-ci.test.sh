#!/usr/bin/env bash
# #1760 (spec #1733): setup-python-repo copies no GitHub Actions workflow and
# sets the merge gate with `git config land.testcmd` (flow/claude/WORKFLOW.md
# § CI). Blind to: whether a model following the prose then sets the gate.
set -uo pipefail
root=$(git rev-parse --show-toplevel) || exit 1
d=$root/setup-python-repo
fail=0
bad() { echo "FAIL: $1"; fail=1; }
[ -e "$d/templates/ci.yml" ] && bad "templates/ci.yml still exists"
[ -e "$d/templates/clear-in-review.yml" ] && bad "templates/clear-in-review.yml still exists"
if grep -rnE 'ci\.yml|\.github/workflows|clear-in-review' "$d" --include='*.md'; then
  bad "setup-python-repo still names a workflow file"
fi
if sed -n 3p "$d/SKILL.md" | grep -q "GitHub Actions"; then
  bad "SKILL.md description still lists GitHub Actions"
fi
grep -q "git config land.testcmd 'just check'" "$d/SKILL.md" || bad "SKILL.md does not set the gate with git config land.testcmd"
[ "$fail" -eq 0 ] && echo "PASS: setup-python-repo sets no CI workflow"
exit "$fail"
