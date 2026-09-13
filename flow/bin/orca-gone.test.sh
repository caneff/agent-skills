#!/usr/bin/env bash
# Fixture tests for this check script: two mktemp trees, one planted hit and
# one clean, each with its own $HOME so the real machine is never touched.
# Every fixture string below is built from the split needle, not spelled
# out, so this file matches nothing when the script under test scans the
# real repo. Run this file directly with bash from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
needle='or''ca'
script="$here/${needle}-gone"
fails=0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# A clean fixture: an empty repo, an empty worktree dir, no AGENTS.md hits.
clean="$tmp/clean"
mkdir -p "$clean/repo" "$clean/home/.claude" "$clean/home/.local/bin" \
         "$clean/home/src/some-project" "$clean/home/$needle/workspaces"
echo "nothing to see here" > "$clean/repo/README.md"
echo "clean" > "$clean/home/.claude/CLAUDE.md"
echo "clean" > "$clean/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$clean/repo" \
      GONE_HOME_CLAUDE_MD="$clean/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$clean/home/.local/bin" \
      GONE_SRC_DIR="$clean/home/src" \
      GONE_WORKSPACES_DIR="$clean/home/$needle/workspaces" \
      HOME="$clean/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "^PASS"; then
  echo "PASS a clean fixture with an empty worktree dir exits 0"
else
  echo "FAIL clean fixture: rc=$rc out=$out"; fails=1
fi

# A fixture with one planted hit in the repo scan, and a non-empty worktree
# dir — both should be reported, and the exit should be non-zero.
dirty="$tmp/dirty"
mkdir -p "$dirty/repo" "$dirty/home/.claude" "$dirty/home/.local/bin" \
         "$dirty/home/src/some-project" "$dirty/home/$needle/workspaces/leftover-repo"
echo "call ${needle}-ide worktree rm here" > "$dirty/repo/leftover.sh"
echo "clean" > "$dirty/home/.claude/CLAUDE.md"
echo "clean" > "$dirty/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$dirty/repo" \
      GONE_HOME_CLAUDE_MD="$dirty/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$dirty/home/.local/bin" \
      GONE_SRC_DIR="$dirty/home/src" \
      GONE_WORKSPACES_DIR="$dirty/home/$needle/workspaces" \
      HOME="$dirty/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "leftover.sh" \
   && printf '%s' "$out" | grep -q "not empty"; then
  echo "PASS a planted hit and a non-empty worktree dir both fail and list"
else
  echo "FAIL dirty fixture: rc=$rc out=$out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
