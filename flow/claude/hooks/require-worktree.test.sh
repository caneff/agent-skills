#!/bin/bash
# Contract test for require-worktree.sh: feed it PreToolUse JSON, check verdicts.
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/require-worktree.sh"
fails=0

check() { # check <desc> <expected-exit> <file-path>
  printf '{"tool_input":{"file_path":"%s"}}' "$2" | "$HOOK" >/dev/null 2>&1
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

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
