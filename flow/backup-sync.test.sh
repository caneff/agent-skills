#!/usr/bin/env bash
# Contract test for backup-sync.sh (#1031): claude/settings.json moved off
# the copy-only manifest (install.sh symlinks it now, previous commit), so
# --restore must not touch it at all, while --commit must still pick up and
# push a harness write that landed on it through the link.
#
# Every case below runs a scratch COPY of backup-sync.sh with its
# vscode/settings.json entry redirected under $tmp first (#1031 review
# finding C1/P2): the real entry is an absolute /mnt/c/... path that ignores
# $HOME, so running the unpatched script's --restore against a live machine
# overwrites the operator's real Windows VS Code settings — confirmed on this
# box (mtime moved to the run's own minute) before this redirect was added.
# Run: bash flow/backup-sync.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# A scratch repo: backup-sync.sh's own dir doubles as the git repo `--commit`
# operates on ($here inside the script), so each case gets its own git-init'd
# copy rather than ever touching this real checkout.
scratch_repo() { # scratch_repo <dir> -> writes a patched backup-sync.sh + fixtures, git-inits it
  local dir="$1"
  mkdir -p "$dir/claude/output-styles" "$dir/vscode" "$dir/fake-vscode"
  printf '{"env":{}}\n' > "$dir/claude/settings.json"
  printf '# quill\n' > "$dir/claude/output-styles/quill.md"
  printf '{"vscode":true}\n' > "$dir/vscode/settings.json"
  # The real live path is a pre-existing file the glob matches; a glob over a
  # not-yet-created path matches nothing, so the redirected fake live file
  # has to already exist too, or every case below silently skips it. Starts
  # identical to the repo copy (already "synced") so a case that only cares
  # about claude/settings.json doesn't pick up a spurious vscode commit too.
  printf '{"vscode":true}\n' > "$dir/fake-vscode/settings.json"
  # Redirect the one entry whose live path is absolute and machine-real.
  sed 's#/mnt/c/Users/\*/AppData/Roaming/Code/User/settings.json#'"$dir"'/fake-vscode/settings.json#' \
    "$here/backup-sync.sh" > "$dir/backup-sync.sh"
  chmod +x "$dir/backup-sync.sh"
  git -C "$dir" init -q
  git -C "$dir" config user.name t
  git -C "$dir" config user.email t@example.com
  git -C "$dir" add -A
  git -C "$dir" commit -q -m base
}

# --restore must not touch a symlinked settings.json: it is no longer in the
# manifest, install.sh owns the link, and a copy through it would clobber
# whatever the harness has written since.
restore="$tmp/restore"; scratch_repo "$restore"
printf '{"vscode":"stale-live"}\n' > "$restore/fake-vscode/settings.json"
mkdir -p "$tmp/restore-home/.claude"
printf 'SENTINEL\n' > "$tmp/restore-home/.claude/settings-target.json"
ln -s "$tmp/restore-home/.claude/settings-target.json" "$tmp/restore-home/.claude/settings.json"
out=$(HOME="$tmp/restore-home" bash "$restore/backup-sync.sh" --restore 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then
  echo "PASS backup-sync.sh --restore exits 0 with a symlinked settings.json in place"
else
  echo "FAIL backup-sync.sh --restore exited $rc: $out"; fails=1
fi
if [ -L "$tmp/restore-home/.claude/settings.json" ] \
   && [ "$(readlink "$tmp/restore-home/.claude/settings.json")" = "$tmp/restore-home/.claude/settings-target.json" ] \
   && [ "$(cat "$tmp/restore-home/.claude/settings-target.json")" = SENTINEL ]; then
  echo "PASS --restore leaves the settings.json symlink and its content intact"
else
  echo "FAIL --restore touched settings.json: $(ls -la "$tmp/restore-home/.claude/settings.json" 2>&1) $(cat "$tmp/restore-home/.claude/settings-target.json" 2>&1)"; fails=1
fi
if [ "$(cat "$restore/fake-vscode/settings.json")" = '{"vscode":true}' ]; then
  echo "PASS the vscode entry restores under the scratch repo, never a real machine path"
else
  echo "FAIL the vscode redirect did not take effect as expected: $(cat "$restore/fake-vscode/settings.json")"; fails=1
fi

# --commit must still pick up a harness write to claude/settings.json (#1031
# P1): install.sh symlinks it, so the harness now writes straight into the
# repo file, and nothing else backs that write up once it is out of the
# copy-based manifest — --commit has to stage and commit it directly.
commit="$tmp/commit"; scratch_repo "$commit"
printf '{"env":{"CHANGED":true}}\n' > "$commit/claude/settings.json"
before_sha=$(git -C "$commit" rev-parse HEAD)
out=$(HOME="$tmp/commit-home" bash "$commit/backup-sync.sh" --commit 2>&1); rc=$?
after_sha=$(git -C "$commit" rev-parse HEAD)
if [ "$rc" -eq 0 ] && [ "$after_sha" != "$before_sha" ] \
   && git -C "$commit" show --stat HEAD | grep -q 'claude/settings.json'; then
  echo "PASS --commit commits a harness write to claude/settings.json"
else
  echo "FAIL --commit did not commit the settings.json change (rc=$rc, before=$before_sha, after=$after_sha): $out"; fails=1
fi

# An unchanged settings.json must not force an empty commit.
noop="$tmp/noop"; scratch_repo "$noop"
before_sha=$(git -C "$noop" rev-parse HEAD)
HOME="$tmp/noop-home" bash "$noop/backup-sync.sh" --commit >/dev/null 2>&1
after_sha=$(git -C "$noop" rev-parse HEAD)
if [ "$after_sha" = "$before_sha" ]; then
  echo "PASS --commit with no changes makes no commit"
else
  echo "FAIL --commit made an empty commit when nothing changed"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
