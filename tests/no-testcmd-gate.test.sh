#!/usr/bin/env bash
# #1881: a repo's merge gate is the command its AGENTS.md `## End-to-end seam`
# section names; no merge path reads `git config land.testcmd` (Chris, 2026-11-14;
# drain/drain_test.py pins it). Only the files that state that fact may name the
# key, so a skill or comment cannot call it the gate again.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1
allowed='^(flow/claude/WORKFLOW\.md|drain/drain_test\.py|setup-python-repo/SKILL\.md|tests/no-testcmd-gate\.test\.sh|docs/research/.*)$'
files=$(git ls-files -z | xargs -0 grep -l 'land\.testcmd' 2>/dev/null) || files=""
bad=$(printf '%s\n' "$files" | grep -v '^$' | grep -Ev "$allowed" || true)
if [ -n "$bad" ]; then
  echo "FAIL: land.testcmd named outside the files that say no merge reads it:" >&2
  printf '%s\n' "$bad" >&2
  exit 1
fi
# The files allowed to name it must still say it is not the gate.
grep -q 'read by no merge path' flow/claude/WORKFLOW.md || { echo "FAIL: WORKFLOW.md § CI lost its land.testcmd statement" >&2; exit 1; }
grep -q 'Nothing reads' setup-python-repo/SKILL.md || { echo "FAIL: setup-python-repo/SKILL.md lost its land.testcmd statement" >&2; exit 1; }
echo "PASS no-testcmd-gate"
