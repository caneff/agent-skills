#!/bin/bash
# Cross-repo worktree guard (PreToolUse, EnterWorktree).
#
# EnterWorktree with a `path` in a DIFFERENT repo than the session's cwd always
# raises a permission prompt: the harness calls it a permission-root relocation
# and marks it classifierApprovable:false, so no allow rule and no auto mode can
# silence it. Only the user can. This hook blocks that call before it prompts,
# and points the agent at the route that never prompts: spawn an Agent with
# `cwd` set to the other repo and let it enter its own worktree there.
#
# Same-repo paths (the managed .claude/worktrees/ case) pass untouched, and so
# does a call with no `path` — creating a worktree by `name` never prompts.

INPUT=$(cat)
path=$(echo "$INPUT" | jq -r '.tool_input.path // ""')
[ -n "$path" ] || exit 0

cwd=$(echo "$INPUT" | jq -r '.cwd // ""')
[ -n "$cwd" ] || exit 0

# Compare common dirs, not toplevels: every linked worktree of a repo shares one
# common dir, so a sibling worktree of the same repo reads as same-repo.
here=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
there=$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
[ -n "$here" ] && [ -n "$there" ] || exit 0
[ "$here" = "$there" ] && exit 0

echo "BLOCKED: '$path' is a worktree of another repo. EnterWorktree across repos always prompts the user, and no setting can pre-approve it. Spawn an Agent with cwd set to that repo instead, and let it EnterWorktree there." >&2
exit 2
