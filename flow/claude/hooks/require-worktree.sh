#!/bin/bash
# Worktree guard (PreToolUse, Edit|Write).
#
# Every agent that touches a repo file works in a linked worktree — never the
# primary checkout. This hook enforces it: an Edit/Write whose target resolves
# (symlinks included, so ~/.claude/CLAUDE.md counts) into a repo's PRIMARY
# checkout is blocked with "EnterWorktree first". Files outside any git repo
# (job dirs, /tmp, scratch) and files inside linked worktrees pass untouched.
# Bash-side writes are out of scope; this catches the dominant edit path.

INPUT=$(cat)
path=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
[ -n "$path" ] || exit 0

# Resolve symlinks so an edit through a live symlink is judged by its target.
real=$(realpath -m "$path" 2>/dev/null) || exit 0
dir=$(dirname "$real")

git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# --path-format=absolute: --git-common-dir is otherwise relative to -C's cwd.
git_dir=$(git -C "$dir" rev-parse --path-format=absolute --git-dir 2>/dev/null) || exit 0
common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
[ -n "$git_dir" ] && [ -n "$common" ] || exit 0

# Linked worktree: its git-dir differs from the repo's common dir. Allowed.
[ "$git_dir" != "$common" ] && exit 0

echo "BLOCKED: '$path' is in a repo's PRIMARY checkout. Agents touch repo files only from a linked worktree — run EnterWorktree first, do the work there, then land it. This applies to docs too." >&2
exit 2
