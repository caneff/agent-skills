#!/usr/bin/env bash
# Point the live flow-tooling locations at this repo, so the repo is the single
# source of truth and every commit backs them up. Run once on a fresh machine
# (after cloning agent-skills), or after adding a new file here.
#
# Idempotent: re-running is safe. A real file already at a destination is moved
# aside to <file>.pre-flow once, then replaced by the symlink — nothing is lost.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

link() { # link <repo-relative-src> <live-dest>
  local src="$here/$1" dest="$2"
  [ -e "$src" ] || { echo "missing in repo: $1" >&2; return 1; }
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    rm "$dest"
  elif [ -e "$dest" ]; then
    mv "$dest" "$dest.pre-flow"
    echo "backed up existing $dest -> $dest.pre-flow"
  fi
  ln -s "$src" "$dest"
  echo "linked $dest -> $src"
}

link bin/issue-counts           "$HOME/.local/bin/issue-counts"
link bin/merge-cleanup          "$HOME/.local/bin/merge-cleanup"
link claude/CLAUDE.md           "$HOME/.claude/CLAUDE.md"
link claude/RTK.md              "$HOME/.claude/RTK.md"
# claude/settings.json is NOT symlinked — the harness rewrites it in place and
# would break the link. It is a copy-only backup (see backup-sync.sh), written
# by the --restore call below.
link claude/settings.local.json "$HOME/.claude/settings.local.json"
for h in block-dangerous-git.sh refresh-landed.sh require-agent-model.sh package.json; do
  link "claude/hooks/$h" "$HOME/.claude/hooks/$h"
done
for a in "$here/claude/agents"/*.md; do
  link "claude/agents/$(basename "$a")" "$HOME/.claude/agents/$(basename "$a")"
done
# Renamed from sync-primary-main.sh to refresh-landed.sh: drop the stale
# symlink so a rename doesn't leave the old name pointing into this repo.
if [ -L "$HOME/.claude/hooks/sync-primary-main.sh" ]; then
  rm -f "$HOME/.claude/hooks/sync-primary-main.sh"
fi

# The pre-push hook that ran tests/all.sh is retired (#633): a push is not the
# gate, the merge is (`git config land.testcmd`), and the hook's own GIT_DIR
# leaked into the suite. Drop the symlink an earlier install left. Hooks are
# shared across worktrees, so resolve the common git dir rather than ".git".
git_common_dir="$(git -C "$here/.." rev-parse --path-format=absolute --git-common-dir)"
if [ -L "$git_common_dir/hooks/pre-push" ]; then
  rm -f "$git_common_dir/hooks/pre-push"
  echo "removed retired pre-push hook"
fi

# Lay down the copy-only backups (files a symlink can't hold): the Windows VS
# Code settings and claude/settings.json.
bash "$here/backup-sync.sh" --restore

echo
echo "Done. The live flow tooling now points at this repo; commit to back it up."
