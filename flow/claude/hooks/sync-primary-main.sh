#!/usr/bin/env bash
# PostToolUse(Bash) hook: keep the PRIMARY git worktree's local `main` fresh.
#
# Topology: this repo uses git worktrees. The primary clone (real .git/) lives
# at $PRIMARY below and keeps `main` checked out but parked. Day-to-day work
# happens in sibling worktrees (ttd-claude, ttd-codex) on feature branches.
# When a feature worktree pushes to origin/main, the primary's local `main`
# ref falls behind. This hook fast-forwards it back in sync after such a push.
#
# Contract: read the Bash tool-call JSON on stdin; if the command pushed to
# `main`, fast-forward the primary worktree to origin/main. Otherwise do
# nothing. Always exit 0 — never block the turn, never produce a merge commit.

set -u

PRIMARY=/home/caneff/src/talk-to-your-data-slackbot

# The command that just ran (empty string if absent / jq missing).
cmd="$(jq -r '.tool_input.command // ""' 2>/dev/null)"

# Cheap pre-filter: bail unless this was a push. A stray match only costs a
# ~1s regen.
case "$cmd" in
  *push*) ;;
  *) exit 0 ;;
esac

# Any push: refresh the landed review page in the background (~1s, 0 tokens).
python3 /home/caneff/.agents/skills/landed/generate.py >/dev/null 2>&1 &

# Only act when the push destination is `main`. Matches a refspec ending in
# `:main` (e.g. `HEAD:main`, `main:main`) or `main` as a standalone pushed ref
# (e.g. `origin main`), each bounded by whitespace or end-of-string so that
# `mainline`, `feature-main`, etc. do not false-positive.
echo "$cmd" | grep -Eq '(:main([[:space:]]|$)|[[:space:]]main([[:space:]]|$))' || exit 0

# Only act if the primary worktree is actually present.
[ -d "$PRIMARY" ] || exit 0

# Fast-forward only: a no-op (never destructive, never a merge commit) if the
# primary's main is dirty or has diverged. Errors are swallowed so a transient
# fetch failure can never block the turn.
git -C "$PRIMARY" fetch origin --quiet 2>/dev/null || true
git -C "$PRIMARY" merge --ff-only origin/main --quiet 2>/dev/null || true

exit 0
