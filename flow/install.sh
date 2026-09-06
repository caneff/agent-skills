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
link claude/CLAUDE.md           "$HOME/.claude/CLAUDE.md"
link claude/RTK.md              "$HOME/.claude/RTK.md"
# claude/settings.json is NOT symlinked — the harness rewrites it in place and
# would break the link. It is a copy-only backup (see backup-sync.sh), written
# by the --restore call below.
link claude/settings.local.json "$HOME/.claude/settings.local.json"
for h in block-dangerous-git.sh sync-primary-main.sh package.json; do
  link "claude/hooks/$h" "$HOME/.claude/hooks/$h"
done

link ccstatusline/settings.json          "$HOME/.config/ccstatusline/settings.json"
link ccstatusline/issue-counts-segment.sh "$HOME/.config/ccstatusline/issue-counts-segment.sh"

# Pre-push hook: refuse a push when tests/all.sh fails. Hooks are shared
# across worktrees, so resolve the common git dir rather than assuming ".git".
git_common_dir="$(git -C "$here/.." rev-parse --path-format=absolute --git-common-dir)"
link ../tests/all.sh "$git_common_dir/hooks/pre-push"

# Lay down the copy-only backups (files a symlink can't hold): the Windows VS
# Code settings and claude/settings.json.
bash "$here/backup-sync.sh" --restore

echo
echo "Done. The live flow tooling now points at this repo; commit to back it up."
