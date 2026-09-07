#!/usr/bin/env bash
# Contract test for install.sh's hook handling: run it from a scratch clone
# with HOME pointed at a scratch dir, so nothing live is touched. Asserts the
# retired pre-push symlink (tests/all.sh) is removed and never re-created
# (#633) — the merge gate (git config land.testcmd) is where tests/all.sh runs.
# Run: bash flow/install.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

# A scratch repo holding only what install.sh links, plus a stale pre-push hook
# left by an earlier install.
repo="$tmp/repo"
mkdir -p "$repo/tests"
cp -r "$root/flow" "$repo/flow"
cp "$root/tests/all.sh" "$repo/tests/all.sh"
git -C "$repo" init -q
ln -s "$repo/flow/../tests/all.sh" "$repo/.git/hooks/pre-push"
# backup-sync.sh --restore writes to absolute live paths (the Windows VS Code
# settings), not $HOME, so the scratch copy is a no-op.
printf '#!/usr/bin/env bash\nexit 0\n' > "$repo/flow/backup-sync.sh"

fails=0
out=$(HOME="$tmp/home" bash "$repo/flow/install.sh" 2>&1) || { echo "FAIL install.sh exited non-zero"; printf '%s\n' "$out"; fails=1; }

if [ -e "$repo/.git/hooks/pre-push" ] || [ -L "$repo/.git/hooks/pre-push" ]; then
  echo "FAIL .git/hooks/pre-push still present after install"; fails=1
else
  echo "PASS stale pre-push hook removed"
fi
if printf '%s' "$out" | grep -q 'hooks/pre-push'; then
  echo "FAIL install.sh still links a pre-push hook"; fails=1
else
  echo "PASS no pre-push hook linked"
fi
if [ -L "$tmp/home/.claude/hooks/refresh-landed.sh" ]; then
  echo "PASS live hooks still linked under the scratch HOME"
else
  echo "FAIL refresh-landed.sh not linked under the scratch HOME"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
