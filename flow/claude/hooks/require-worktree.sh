#!/bin/bash
# Worktree guard (PreToolUse, Edit|Write).
#
# Every agent that touches a repo file works in a linked worktree — never the
# primary checkout. This hook enforces it: an Edit/Write whose target resolves
# (symlinks included, so ~/.claude/CLAUDE.md counts) into a repo's PRIMARY
# checkout is blocked with "EnterWorktree first". Files outside any git repo
# (job dirs, /tmp, scratch) pass untouched. Files inside linked worktrees pass
# only for the session that owns the worktree (claim-on-first-write, below).
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

# Linked worktree: its git-dir differs from the repo's common dir. Allowed —
# but only for the session that owns it. Ownership is claim-on-first-write:
# the first session to edit in a worktree stamps its session_id into the
# worktree's private git dir; a different session is blocked. No session_id
# in the input (manual test, old harness) skips the check.
if [ "$git_dir" != "$common" ]; then
  session=$(echo "$INPUT" | jq -r '.session_id // ""')
  [ -n "$session" ] || exit 0
  owner_file="$git_dir/agent-owner"
  if [ -f "$owner_file" ]; then
    owner=$(cat "$owner_file")
    if [ "$owner" != "$session" ]; then
      echo "BLOCKED: the worktree holding '$path' belongs to another agent (session $owner). Work in your own worktree — EnterWorktree first. If that session is dead and you are taking over on purpose, rm '$owner_file' and retry." >&2
      exit 2
    fi
  else
    echo "$session" > "$owner_file"
  fi
  exit 0
fi

echo "BLOCKED: '$path' is in a repo's PRIMARY checkout. Agents touch repo files only from a linked worktree — run EnterWorktree first, do the work there, then land it. This applies to docs too." >&2
exit 2
