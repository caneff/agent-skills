#!/bin/bash
# Contract test for require-worktree.sh: feed it PreToolUse JSON, check verdicts.
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/require-worktree.sh"
fails=0

check() { # check <expected-exit> <file-path> <desc> [session-id]
  if [ -n "${4:-}" ]; then
    printf '{"session_id":"%s","tool_input":{"file_path":"%s"}}' "$4" "$2" | "$HOOK" >/dev/null 2>&1
  else
    printf '{"tool_input":{"file_path":"%s"}}' "$2" | "$HOOK" >/dev/null 2>&1
  fi
  got=$?
  if [ "$got" = "$1" ]; then echo "PASS: $3"; else echo "FAIL: $3 (exit $got, want $1)"; fails=1; fi
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git init -q "$tmp/repo" && cd "$tmp/repo" || exit 1
git commit -q --allow-empty -m init
git worktree add -q "$tmp/wt" -b test-branch

check 2 "$tmp/repo/file.txt"      "primary checkout blocked"
check 0 "$tmp/wt/file.txt"        "linked worktree allowed"
check 0 "$tmp/outside.txt"        "non-repo path allowed"
mkdir -p "$tmp/repo/sub"
check 2 "$tmp/repo/sub/new.txt"   "new file in primary subdir blocked"
ln -s "$tmp/repo/file.txt" "$tmp/link.txt"
check 2 "$tmp/link.txt"           "symlink into primary blocked"

# Ownership: first session to write claims the worktree; others are blocked.
check 0 "$tmp/wt/file.txt"        "first session claims worktree"      sess-A
check 0 "$tmp/wt/file.txt"        "owning session allowed again"       sess-A
check 2 "$tmp/wt/file.txt"        "other session blocked"              sess-B
check 0 "$tmp/wt/file.txt"        "no session_id skips owner check"

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
