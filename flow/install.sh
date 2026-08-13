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

link bin/ship                   "$HOME/.local/bin/ship"
link bin/pushpr                 "$HOME/.local/bin/pushpr"
link claude/CLAUDE.md           "$HOME/.claude/CLAUDE.md"
link claude/RTK.md              "$HOME/.claude/RTK.md"
link claude/settings.json       "$HOME/.claude/settings.json"
link claude/settings.local.json "$HOME/.claude/settings.local.json"
for h in block-dangerous-git.sh sync-main-after-merge.sh sync-primary-main.sh package.json; do
  link "claude/hooks/$h" "$HOME/.claude/hooks/$h"
done

echo
echo "Done. The live flow tooling now points at this repo; commit to back it up."
