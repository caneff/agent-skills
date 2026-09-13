#!/usr/bin/env bash
# Fixture tests for this check script: two mktemp trees, one planted hit and
# one clean, each with its own $HOME so the real machine is never touched.
# Every fixture string below is built from the split needle, not spelled
# out, so this file matches nothing when the script under test scans the
# real repo. Run this file directly with bash from flow/bin/.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
needle='or''ca'
script="$here/${needle}-gone"
fails=0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# A clean fixture: an empty repo, an empty worktree dir, no AGENTS.md hits.
clean="$tmp/clean"
mkdir -p "$clean/repo" "$clean/home/.claude" "$clean/home/.local/bin" \
         "$clean/home/src/some-project" "$clean/home/$needle/workspaces"
echo "nothing to see here" > "$clean/repo/README.md"
echo "clean" > "$clean/home/.claude/CLAUDE.md"
echo "clean" > "$clean/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$clean/repo" \
      GONE_HOME_CLAUDE_MD="$clean/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$clean/home/.local/bin" \
      GONE_SRC_DIR="$clean/home/src" \
      GONE_WORKSPACES_DIR="$clean/home/$needle/workspaces" \
      HOME="$clean/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "^PASS"; then
  echo "PASS a clean fixture with an empty worktree dir exits 0"
else
  echo "FAIL clean fixture: rc=$rc out=$out"; fails=1
fi

# A fixture with one planted hit in the repo scan, and a non-empty worktree
# dir — both should be reported, and the exit should be non-zero.
dirty="$tmp/dirty"
mkdir -p "$dirty/repo" "$dirty/home/.claude" "$dirty/home/.local/bin" \
         "$dirty/home/src/some-project" "$dirty/home/$needle/workspaces/leftover-repo"
echo "call ${needle}-ide worktree rm here" > "$dirty/repo/leftover.sh"
echo "clean" > "$dirty/home/.claude/CLAUDE.md"
echo "clean" > "$dirty/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$dirty/repo" \
      GONE_HOME_CLAUDE_MD="$dirty/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$dirty/home/.local/bin" \
      GONE_SRC_DIR="$dirty/home/src" \
      GONE_WORKSPACES_DIR="$dirty/home/$needle/workspaces" \
      HOME="$dirty/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "leftover.sh" \
   && printf '%s' "$out" | grep -q "not empty"; then
  echo "PASS a planted hit and a non-empty worktree dir both fail and list"
else
  echo "FAIL dirty fixture: rc=$rc out=$out"; fails=1
fi

# A hit in ~/.claude/CLAUDE.md alone (repo and everything else clean).
claude_md_hit="$tmp/claude_md_hit"
mkdir -p "$claude_md_hit/repo" "$claude_md_hit/home/.claude" "$claude_md_hit/home/.local/bin" \
         "$claude_md_hit/home/src/some-project" "$claude_md_hit/home/$needle/workspaces"
echo "nothing to see here" > "$claude_md_hit/repo/README.md"
echo "the ${needle}-ide flow lives here" > "$claude_md_hit/home/.claude/CLAUDE.md"
echo "clean" > "$claude_md_hit/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$claude_md_hit/repo" \
      GONE_HOME_CLAUDE_MD="$claude_md_hit/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$claude_md_hit/home/.local/bin" \
      GONE_SRC_DIR="$claude_md_hit/home/src" \
      GONE_WORKSPACES_DIR="$claude_md_hit/home/$needle/workspaces" \
      HOME="$claude_md_hit/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "CLAUDE.md"; then
  echo "PASS a hit in ~/.claude/CLAUDE.md fails and names the file"
else
  echo "FAIL CLAUDE.md fixture: rc=$rc out=$out"; fails=1
fi

# A hit inside ~/.local/bin alone.
local_bin_hit="$tmp/local_bin_hit"
mkdir -p "$local_bin_hit/repo" "$local_bin_hit/home/.claude" "$local_bin_hit/home/.local/bin" \
         "$local_bin_hit/home/src/some-project" "$local_bin_hit/home/$needle/workspaces"
echo "nothing to see here" > "$local_bin_hit/repo/README.md"
echo "clean" > "$local_bin_hit/home/.claude/CLAUDE.md"
printf '#!/usr/bin/env bash\necho stub for %s-wait\n' "$needle" > "$local_bin_hit/home/.local/bin/some-script"
echo "clean" > "$local_bin_hit/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$local_bin_hit/repo" \
      GONE_HOME_CLAUDE_MD="$local_bin_hit/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$local_bin_hit/home/.local/bin" \
      GONE_SRC_DIR="$local_bin_hit/home/src" \
      GONE_WORKSPACES_DIR="$local_bin_hit/home/$needle/workspaces" \
      HOME="$local_bin_hit/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "some-script"; then
  echo "PASS a hit in ~/.local/bin fails and names the file"
else
  echo "FAIL local_bin fixture: rc=$rc out=$out"; fails=1
fi

# A hit inside an AGENTS.md reached only through a symlinked ~/src.
symlinked_src="$tmp/symlinked_src"
mkdir -p "$symlinked_src/repo" "$symlinked_src/home/.claude" "$symlinked_src/home/.local/bin" \
         "$symlinked_src/real-src/some-project" "$symlinked_src/home/$needle/workspaces"
ln -s "$symlinked_src/real-src" "$symlinked_src/home/src"
echo "nothing to see here" > "$symlinked_src/repo/README.md"
echo "clean" > "$symlinked_src/home/.claude/CLAUDE.md"
echo "the ${needle}-auto-enter helper" > "$symlinked_src/real-src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$symlinked_src/repo" \
      GONE_HOME_CLAUDE_MD="$symlinked_src/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$symlinked_src/home/.local/bin" \
      GONE_SRC_DIR="$symlinked_src/home/src" \
      GONE_WORKSPACES_DIR="$symlinked_src/home/$needle/workspaces" \
      HOME="$symlinked_src/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "AGENTS.md"; then
  echo "PASS a hit behind a symlinked ~/src is still found"
else
  echo "FAIL symlinked ~/src fixture: rc=$rc out=$out"; fails=1
fi

# rg missing from PATH must fail loudly, never pass by having searched nothing.
no_rg="$tmp/no_rg"
mkdir -p "$no_rg/repo" "$no_rg/home/.claude" "$no_rg/home/.local/bin" \
         "$no_rg/home/src/some-project" "$no_rg/home/$needle/workspaces" "$no_rg/emptypath"
echo "call ${needle}-ide worktree rm here" > "$no_rg/repo/leftover.sh"
echo "clean" > "$no_rg/home/.claude/CLAUDE.md"
echo "clean" > "$no_rg/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$no_rg/repo" \
      GONE_HOME_CLAUDE_MD="$no_rg/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$no_rg/home/.local/bin" \
      GONE_SRC_DIR="$no_rg/home/src" \
      GONE_WORKSPACES_DIR="$no_rg/home/$needle/workspaces" \
      HOME="$no_rg/home" PATH="$no_rg/emptypath" "$(command -v bash)" "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -qi "rg"; then
  echo "PASS a missing rg fails loudly instead of a false pass"
else
  echo "FAIL no-rg fixture: rc=$rc out=$out"; fails=1
fi

# A vendored node_modules tree with a coincidental case-insensitive hit
# (a camelCase identifier straddling two words) must not fail the check —
# it isn't a real reference, only a substring collision.
vendored="$tmp/vendored"
mkdir -p "$vendored/repo/node_modules/some-pkg" "$vendored/home/.claude" \
         "$vendored/home/.local/bin" "$vendored/home/src/some-project" \
         "$vendored/home/$needle/workspaces"
echo "nothing to see here" > "$vendored/repo/README.md"
# Split so the source text never spells the collision contiguously either.
frag1="AccessorC"
frag2="annotHaveThisParameter"
printf 'exports.%s%s = 1;\n' "$frag1" "$frag2" \
  > "$vendored/repo/node_modules/some-pkg/index.js"
echo "clean" > "$vendored/home/.claude/CLAUDE.md"
echo "clean" > "$vendored/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$vendored/repo" \
      GONE_HOME_CLAUDE_MD="$vendored/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$vendored/home/.local/bin" \
      GONE_SRC_DIR="$vendored/home/src" \
      GONE_WORKSPACES_DIR="$vendored/home/$needle/workspaces" \
      HOME="$vendored/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "^PASS"; then
  echo "PASS a coincidental hit inside node_modules does not fail the check"
else
  echo "FAIL vendored fixture: rc=$rc out=$out"; fails=1
fi

# An unreadable ~/src must fail loud, not silently skip the AGENTS.md sweep.
unreadable_src="$tmp/unreadable_src"
mkdir -p "$unreadable_src/repo" "$unreadable_src/home/.claude" \
         "$unreadable_src/home/.local/bin" "$unreadable_src/home/src" \
         "$unreadable_src/home/$needle/workspaces"
echo "nothing to see here" > "$unreadable_src/repo/README.md"
echo "clean" > "$unreadable_src/home/.claude/CLAUDE.md"
chmod 000 "$unreadable_src/home/src"

out=$(GONE_REPO_ROOT="$unreadable_src/repo" \
      GONE_HOME_CLAUDE_MD="$unreadable_src/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$unreadable_src/home/.local/bin" \
      GONE_SRC_DIR="$unreadable_src/home/src" \
      GONE_WORKSPACES_DIR="$unreadable_src/home/$needle/workspaces" \
      HOME="$unreadable_src/home" bash "$script" 2>&1)
rc=$?
chmod 700 "$unreadable_src/home/src"
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "could not be entered"; then
  echo "PASS an unreadable ~/src fails loud instead of skipping silently"
else
  echo "FAIL unreadable ~/src fixture: rc=$rc out=$out"; fails=1
fi

# Planted hits in .git/, .claude/worktrees/<name>/ and .scratch/ inside the
# repo scan must all be skipped — these are git's own files, other
# worktrees, and scratch notes, not real references.
excluded_dirs="$tmp/excluded_dirs"
mkdir -p "$excluded_dirs/repo/.git" \
         "$excluded_dirs/repo/.claude/worktrees/implement-999" \
         "$excluded_dirs/repo/.scratch" \
         "$excluded_dirs/home/.claude" "$excluded_dirs/home/.local/bin" \
         "$excluded_dirs/home/src/some-project" "$excluded_dirs/home/$needle/workspaces"
echo "nothing to see here" > "$excluded_dirs/repo/README.md"
echo "ref: refs/heads/${needle}-doc-sweep" > "$excluded_dirs/repo/.git/packed-refs"
echo "call ${needle}-ide worktree rm here" > "$excluded_dirs/repo/.claude/worktrees/implement-999/leftover.sh"
echo "notes about ${needle}-ide from earlier" > "$excluded_dirs/repo/.scratch/notes.txt"
echo "clean" > "$excluded_dirs/home/.claude/CLAUDE.md"
echo "clean" > "$excluded_dirs/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$excluded_dirs/repo" \
      GONE_HOME_CLAUDE_MD="$excluded_dirs/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$excluded_dirs/home/.local/bin" \
      GONE_SRC_DIR="$excluded_dirs/home/src" \
      GONE_WORKSPACES_DIR="$excluded_dirs/home/$needle/workspaces" \
      HOME="$excluded_dirs/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q "^PASS"; then
  echo "PASS planted hits in .git/, .claude/worktrees/ and .scratch/ are skipped"
else
  echo "FAIL excluded_dirs fixture: rc=$rc out=$out"; fails=1
fi

# A planted hit in an ordinary gitignored file elsewhere in the repo (not
# under .git/, .claude/worktrees/ or .scratch/) must still fail the check —
# the exclusion is these specific paths, not a tracked-files-only scan.
ordinary_ignored="$tmp/ordinary_ignored"
mkdir -p "$ordinary_ignored/repo/build" "$ordinary_ignored/home/.claude" \
         "$ordinary_ignored/home/.local/bin" "$ordinary_ignored/home/src/some-project" \
         "$ordinary_ignored/home/$needle/workspaces"
echo "build/" > "$ordinary_ignored/repo/.gitignore"
echo "nothing to see here" > "$ordinary_ignored/repo/README.md"
echo "leftover ${needle}-ide build artifact" > "$ordinary_ignored/repo/build/output.txt"
echo "clean" > "$ordinary_ignored/home/.claude/CLAUDE.md"
echo "clean" > "$ordinary_ignored/home/src/some-project/AGENTS.md"

out=$(GONE_REPO_ROOT="$ordinary_ignored/repo" \
      GONE_HOME_CLAUDE_MD="$ordinary_ignored/home/.claude/CLAUDE.md" \
      GONE_LOCAL_BIN="$ordinary_ignored/home/.local/bin" \
      GONE_SRC_DIR="$ordinary_ignored/home/src" \
      GONE_WORKSPACES_DIR="$ordinary_ignored/home/$needle/workspaces" \
      HOME="$ordinary_ignored/home" bash "$script" 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "output.txt"; then
  echo "PASS a planted hit in an ordinary ignored file still fails"
else
  echo "FAIL ordinary_ignored fixture: rc=$rc out=$out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
