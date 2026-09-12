#!/usr/bin/env bash
# backup-sync — copy-only backups that a repo symlink can't hold, because the
# live file lives on the Windows side of WSL. Walks a manifest of repo<->live
# pairs; one line per file.
#
#   backup-sync.sh            repo <- live   (refresh the snapshots)
#   backup-sync.sh --commit   repo <- live, then commit any that changed (hook use)
#   backup-sync.sh --restore  live <- repo   (write the snapshots onto this machine)
#
# --commit is scoped to the manifest paths, so it never sweeps an unrelated
# working-tree edit into its commit. Never exits nonzero on a missing live file
# (a SessionStart hook must not break the session).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# repo-relative path  ->  live path (first glob match wins). Add a line per file.
# Whole-file copies — keep secrets out of every listed file. claude/settings.json
# is here (not symlinked by install.sh) because the harness rewrites it in place,
# which breaks a symlink; machine-local secrets belong in settings.local.json,
# which stays symlinked and is not copied here.
declare -A COPIES=(
  ["vscode/settings.json"]="/mnt/c/Users/*/AppData/Roaming/Code/User/settings.json"
  ["claude/settings.json"]="$HOME/.claude/settings.json"
  ["claude/output-styles/quill.md"]="$HOME/.claude/output-styles/quill.md"
)

mode=${1:-}
for rel in "${!COPIES[@]}"; do
  repo="$here/$rel"
  # shellcheck disable=SC2086 -- the value is a deliberate glob
  live=$(ls ${COPIES[$rel]} 2>/dev/null | head -1)
  [ -n "$live" ] || { echo "skip $rel: no live file" >&2; continue; }
  if [ "$mode" = --restore ]; then
    mkdir -p "$(dirname "$live")"; cp "$repo" "$live" && echo "restored $rel -> live"
  else
    mkdir -p "$(dirname "$repo")"
    cmp -s "$live" "$repo" || { cp "$live" "$repo"; echo "backed up $rel <- live"; }
  fi
done

if [ "$mode" = --commit ]; then
  rels=("${!COPIES[@]}")
  git -C "$here" add -- "${rels[@]}" 2>/dev/null || true
  if ! git -C "$here" diff --cached --quiet -- "${rels[@]}" 2>/dev/null; then
    git -C "$here" commit -q -m "chore(flow): auto-backup copy-only settings" -- "${rels[@]}"
    echo "committed backup snapshot"
    # A commit that never leaves the machine is not a backup, and it leaves main
    # ahead of origin, which is what makes the next push refuse to
    # fast-forward. Push only from main: the commit above went onto whatever
    # HEAD is, so pushing main from another branch would push the wrong thing.
    # ponytail: a rejected push only warns. Rebasing the user's main from a
    # SessionStart hook is worse than leaving the drift visible.
    if [ "$(git -C "$here" symbolic-ref --quiet --short HEAD)" = main ]; then
      timeout 20 git -C "$here" push -q origin main ||
        echo "backup commit not pushed: it is on this machine only" >&2
    else
      echo "backup commit not pushed: HEAD is not main" >&2
    fi
  fi
fi
