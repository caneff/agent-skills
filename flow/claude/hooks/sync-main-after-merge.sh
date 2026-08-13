#!/usr/bin/env bash
# Fast-forward the main worktree to origin and clean up merged feature branches.
#
# Two modes:
#   * Hook mode (no args): reads PostToolUse JSON on stdin; runs only when the
#     command contained "gh pr merge". (Kept for back-compat; now usually dormant,
#     since the git guardrail blocks agents from merging.)
#   * Standalone (--now): run directly after a manual merge — chained from the
#     /ship handoff line or the `ship` shell function, in the user's own shell.
#
# Safe no-op in repos with no `main` worktree.
set -euo pipefail

if [ "${1:-}" = "--now" ]; then
  cwd="$PWD"
else
  if [ -t 0 ]; then
    echo "sync-main: no hook input on stdin; pass --now to sync directly." >&2
    exit 0
  fi
  input="$(cat)"
  cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // ""')"
  case "$cmd" in
    *"gh pr merge"*) ;;
    *) exit 0 ;;
  esac
  cwd="$(printf '%s' "$input" | jq -r '.cwd // ""')"
  [ -n "$cwd" ] || cwd="$PWD"
fi

# Resolve the worktree currently checked out on `main`.
main_wt="$(git -C "$cwd" worktree list --porcelain 2>/dev/null \
  | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')"

if [ -z "${main_wt:-}" ]; then
  echo "sync-main: no main worktree found; skipping." >&2
  exit 0
fi

git -C "$main_wt" fetch origin --quiet --prune

# Fast-forward main only (never create a merge commit / never force).
if git -C "$main_wt" merge --ff-only origin/main >/dev/null 2>&1; then
  echo "sync-main: fast-forwarded main to origin/main." >&2
elif [ "$(git -C "$main_wt" rev-list --count origin/main..main 2>/dev/null || echo 1)" -gt 0 ]; then
  # main holds commit(s) origin lacks. Two very different sub-cases:
  #   (a) squash-aftermath (the common, self-inflicted one): a commit that landed
  #       directly on local main (a session committing to main, or a vault snapshot
  #       whose push was stranded) later got absorbed into a squash-merge. Its
  #       content is now in origin/main under a NEW sha, so the old local sha is
  #       orphaned but carries nothing unique. `git cherry` marks such commits '-'.
  #       Without healing this, --ff-only fails forever after and every later ship
  #       reports "diverged" — the recurring breakage.
  #   (b) genuine unpushed work: at least one local commit has no equivalent
  #       upstream, so `git cherry` marks it '+'. Resetting would destroy it.
  #
  # Heal (a) by resetting main onto origin/main; refuse (b) and leave main alone.
  if git -C "$main_wt" cherry origin/main main | grep -q '^+'; then
    echo "sync-main: main has unpushed commit(s) origin lacks; left untouched (push or PR them)." >&2
  else
    # Every divergent commit is already upstream. Auto-stash working-tree edits
    # (e.g. an uncommitted vault flush) so the reset can't eat them, reset, reapply.
    # The orphaned local sha remains recoverable via reflog.
    stashed=""
    if ! git -C "$main_wt" diff --quiet || ! git -C "$main_wt" diff --cached --quiet; then
      git -C "$main_wt" stash push --quiet --message "sync-main: pre-reset autostash" && stashed=1
    fi
    git -C "$main_wt" reset --hard origin/main >/dev/null 2>&1
    if [ -n "$stashed" ]; then
      git -C "$main_wt" stash pop --quiet >/dev/null 2>&1 \
        || echo "sync-main: reset main to origin/main, but reapplying your local edits hit a conflict — resolve the marked file(s); edits are safe in 'git stash list'." >&2
    fi
    echo "sync-main: main diverged, but every local commit was already upstream (squash-absorbed); reset main to origin/main." >&2
  fi
else
  # main is strictly behind origin; the ff was blocked by uncommitted local changes
  # (e.g. a working-tree edit to a file the incoming commits also touch). Stash, ff,
  # then reapply — preserving the user's in-progress edits.
  if git -C "$main_wt" stash push --quiet --message "sync-main: auto-stash before ff" 2>/dev/null \
     && git -C "$main_wt" merge --ff-only origin/main >/dev/null 2>&1; then
    if git -C "$main_wt" stash pop --quiet >/dev/null 2>&1; then
      echo "sync-main: fast-forwarded main to origin/main (auto-stashed local edits, reapplied)." >&2
    else
      echo "sync-main: fast-forwarded main, but reapplying your local edits hit a conflict — resolve the marked file(s); your edits are safe in 'git stash list'." >&2
    fi
  else
    # Stash or ff failed for another reason; undo any stash and leave main untouched.
    git -C "$main_wt" stash pop --quiet >/dev/null 2>&1 || true
    echo "sync-main: main behind origin but could not be auto-synced; left untouched." >&2
  fi
fi

# Collect branches checked out in any worktree (cannot be deleted).
checked_out="$(git -C "$main_wt" worktree list --porcelain \
  | awk '/^branch refs\/heads\//{sub("refs/heads/","",$2); print $2}')"

# Delete local branches whose upstream is gone (merged + remote-deleted),
# skipping main and any branch checked out in a worktree.
git -C "$main_wt" for-each-ref --format '%(refname:short) %(upstream:track)' refs/heads \
  | awk '$2=="[gone]"{print $1}' \
  | while IFS= read -r branch; do
      [ "$branch" = "main" ] && continue
      if printf '%s\n' "$checked_out" | grep -qx "$branch"; then
        echo "sync-main: '$branch' has gone upstream but is checked out; skipping delete." >&2
        continue
      fi
      if git -C "$main_wt" branch -D "$branch" >/dev/null 2>&1; then
        echo "sync-main: deleted merged branch '$branch'." >&2
      fi
    done

exit 0
