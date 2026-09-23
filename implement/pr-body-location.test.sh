#!/usr/bin/env bash
# Guards #1052: the worker writes the PR body under the review cache, not the
# worktree's `.scratch/`. A `.scratch/pr-body-<n>.md` left in a worktree made
# `merge-cleanup` refuse the removal on every heavy landing, and the controller
# re-ran it with `--discard` by hand (#969, #975/#983). This is a prose
# assertion over implement/SKILL.md, not a behavioral test: nothing runs the
# skill's own prose. The other half — `merge-cleanup` still refusing a
# `.scratch/` file — is pinned in flow/lane/tests/merge_cleanup.rs.
# Resolved via BASH_SOURCE, not git, so a leaked GIT_DIR cannot redirect it (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

for heading in '^### The PR$' '^### The merge$'; do
  grep -q "$heading" "$skill" || { echo "FAIL: implement/SKILL.md has no heading matching $heading" >&2; exit 1; }
done
pr_flat="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
[ -n "$pr_flat" ] || { echo "FAIL: could not extract § The PR from implement/SKILL.md" >&2; exit 1; }

fail=0
case "$pr_flat" in
  *'~/.cache/agent-reviews/<repo>/pr-body-<n>.md'*) ;;
  *) echo "FAIL: § The PR does not put the body at ~/.cache/agent-reviews/<repo>/pr-body-<n>.md" >&2; fail=1 ;;
esac
case "$pr_flat" in
  *'--body-file ~/.cache/agent-reviews/<repo>/pr-body-<n>.md'*) ;;
  *) echo "FAIL: § The PR's gh pr create does not pass that path as --body-file" >&2; fail=1 ;;
esac
# The old rule sent every --body-file to .scratch/; it must not survive for the PR body.
case "$(flatten < "$skill")" in
  *'That is every `--body-file` for `gh pr create`'*) echo "FAIL: the .scratch/ rule still claims every --body-file for gh pr create" >&2; fail=1 ;;
esac
[ "$fail" -eq 0 ] || exit 1
echo "ok: PR body lives in the review cache"
