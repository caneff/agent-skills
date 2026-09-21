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

# cargo install (run by lane-install.sh) needs its own real cache — captured
# before HOME is overridden below — so a scratch HOME does not force a
# from-scratch, possibly offline, rebuild of every dependency.
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}" RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"

# Every case installs from its own scratch repo: a copy of flow/ plus the
# tests/all.sh install.sh's pre-push cleanup looks for, git-init'd with no
# commits, and a no-op backup-sync.sh (--restore writes to absolute live paths,
# the Windows VS Code settings, not $HOME, so the real one is not a no-op).
scratch_repo() { # scratch_repo <dir>
  local dir="$1"
  mkdir -p "$dir/tests"
  cp -r "$root/flow" "$dir/flow"
  rm -rf "$dir/flow/lane/target" # a build cache, not part of the source
  cp "$root/tests/all.sh" "$dir/tests/all.sh"
  git -C "$dir" init -q
  printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/flow/backup-sync.sh"
}

# The first case's repo also carries a stale pre-push hook left by an earlier
# install.
repo="$tmp/repo"
scratch_repo "$repo"
ln -s "$repo/flow/../tests/all.sh" "$repo/.git/hooks/pre-push"

# An earlier install linked merge-cleanup to the bash script this repo no
# longer has; the install must replace that dangling link with the binary.
mkdir -p "$tmp/home/.local/bin"
ln -s "$repo/flow/bin/merge-cleanup" "$tmp/home/.local/bin/merge-cleanup"

# lane-install.sh records the sha it built from at ~/.local/state/lane/build-sha,
# and merge-cleanup reads it as the baseline for "has flow/lane changed since the
# installed binaries were built". This scratch repo has no commits, so HEAD does
# not resolve: the install must still succeed, and must leave no record rather
# than a stale sha or the literal "HEAD" that `git rev-parse` echoes on failure.
sha_file="$tmp/home/.local/state/lane/build-sha"
mkdir -p "$(dirname "$sha_file")"
printf '%s\n' deadbeef > "$sha_file"

fails=0
out=$(HOME="$tmp/home" bash "$repo/flow/install.sh" 2>&1) || { echo "FAIL install.sh exited non-zero"; printf '%s\n' "$out"; fails=1; }

if [ ! -e "$sha_file" ]; then
  echo "PASS an unresolvable HEAD clears the build-sha record instead of recording a bad one"
else
  echo "FAIL build-sha left behind for an unresolvable HEAD: $(cat "$sha_file")"; fails=1
fi

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
# implement-dispatch (#748) is `cargo install`ed, not linked: a real
# executable, never a symlink into the repo, and the fake is never installed.
dispatch_out=$(HOME="$tmp/home" "$tmp/home/.local/bin/implement-dispatch" --repo "$tmp/nowhere" 1 2>&1)
if [ -x "$tmp/home/.local/bin/implement-dispatch" ] && [ ! -L "$tmp/home/.local/bin/implement-dispatch" ] \
   && [ ! -e "$tmp/home/.local/bin/lane-fake" ] \
   && printf '%s' "$dispatch_out" | grep -q "not a git repo"; then
  echo "PASS implement-dispatch installed as a real binary, and the fake is never installed"
else
  echo "FAIL implement-dispatch not installed correctly: $dispatch_out"; fails=1
fi
# merge-cleanup (#749) is `cargo install`ed the same way, and replaces the
# symlink an earlier install left pointing at the deleted bash script.
cleanup_out=$(HOME="$tmp/home" "$tmp/home/.local/bin/merge-cleanup" --repo "$tmp/nowhere" x 2>&1)
if [ -x "$tmp/home/.local/bin/merge-cleanup" ] && [ ! -L "$tmp/home/.local/bin/merge-cleanup" ] \
   && printf '%s' "$cleanup_out" | grep -q "not a git repo"; then
  echo "PASS merge-cleanup installed as a real binary"
else
  echo "FAIL merge-cleanup not installed correctly: $cleanup_out"; fails=1
fi
if [ -L "$tmp/home/.local/bin/job-run" ]; then
  echo "PASS job-run linked onto PATH under the scratch HOME"
else
  echo "FAIL bin/job-run not linked under the scratch HOME"; fails=1
fi
if [ -L "$tmp/home/.claude/hooks/wrap-background-jobs.sh" ]; then
  echo "PASS the background-job hook linked under the scratch HOME"
else
  echo "FAIL claude/hooks/wrap-background-jobs.sh not linked under the scratch HOME"; fails=1
fi
if [ -L "$tmp/home/.claude/hooks/worker-stop-alert.sh" ]; then
  echo "PASS the worker-stop alert hook linked under the scratch HOME"
else
  echo "FAIL claude/hooks/worker-stop-alert.sh not linked under the scratch HOME"; fails=1
fi
if [ -L "$tmp/home/.claude/hooks/worker-spin-alert.sh" ]; then
  echo "PASS the worker-spin alert hook linked under the scratch HOME"
else
  echo "FAIL claude/hooks/worker-spin-alert.sh not linked under the scratch HOME"; fails=1
fi
# Re-running changes nothing: the second install leaves the same symlink, not a
# .pre-flow backup of the first one's.
HOME="$tmp/home" bash "$repo/flow/install.sh" >/dev/null 2>&1
if [ -L "$tmp/home/.local/bin/job-run" ] && [ ! -e "$tmp/home/.local/bin/job-run.pre-flow" ]; then
  echo "PASS installing twice changes nothing"
else
  echo "FAIL a second install left a .pre-flow backup of its own symlink"; fails=1
fi
if [ -L "$tmp/home/.claude/agents/diff-reviewer.md" ]; then
  echo "PASS reviewer agent definition linked under the scratch HOME"
else
  echo "FAIL claude/agents/diff-reviewer.md not linked under the scratch HOME"; fails=1
fi

# An empty claude/agents dir leaves the literal glob; without the guard `link`
# fails it and set -e aborts the install before backup-sync.sh runs.
empty="$tmp/empty"
scratch_repo "$empty"
rm -f "$empty/flow/claude/agents"/*.md
if HOME="$empty/home" bash "$empty/flow/install.sh" >/dev/null 2>&1 \
   && [ -L "$empty/home/.claude/hooks/refresh-landed.sh" ]; then
  echo "PASS an empty claude/agents dir does not abort the install"
else
  echo "FAIL an empty claude/agents dir aborted the install"; fails=1
fi

# The other half of the record: when HEAD does resolve, the install writes that
# sha, so merge-cleanup has a baseline to diff flow/lane against.
recorded="$tmp/recorded"
scratch_repo "$recorded"
git -C "$recorded" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m base
head_sha=$(git -C "$recorded" rev-parse HEAD)
out=$(HOME="$recorded/home" bash "$recorded/flow/install.sh" 2>&1); rc=$?
got=$(cat "$recorded/home/.local/state/lane/build-sha" 2>/dev/null)
if [ "$rc" -ne 0 ]; then
  echo "FAIL install.sh exited non-zero for a repo with a commit (rc=$rc): $out"; fails=1
elif [ "$got" = "$head_sha" ]; then
  echo "PASS the build sha is recorded when HEAD resolves"
else
  echo "FAIL build sha recorded as '$got', want '$head_sha'"; fails=1
fi

# The record is bookkeeping, so nothing in it may abort a completed install —
# not the write, and not the mkdir that precedes it. A fresh HOME whose
# ~/.local/state cannot be written stands in for a read-only or root-owned
# state dir, or a full disk: the record's own mkdir is what fails there.
ro_home="$tmp/ro-home"
mkdir -p "$ro_home/.local/state"
chmod 500 "$ro_home/.local/state"
if [ -w "$ro_home/.local/state" ]; then
  echo "SKIP unwritable state dir (running as root?)"
else
  out=$(HOME="$ro_home" bash "$recorded/flow/install.sh" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && [ -L "$ro_home/.claude/hooks/refresh-landed.sh" ]; then
    echo "PASS an unwritable state dir does not fail the install"
  else
    echo "FAIL an unwritable state dir failed the install (rc=$rc): $out"; fails=1
  fi
fi
chmod 700 "$ro_home/.local/state"

# A failing lane-install.sh (a missing cargo, a compile error) runs last and
# must not half-install everything else — it was never a gate on the rest of
# install.sh before #748, and still is not.
broken="$tmp/broken"
scratch_repo "$broken"
printf '#!/usr/bin/env bash\necho "lane-install: boom" >&2\nexit 1\n' > "$broken/flow/lane-install.sh"
out=$(HOME="$tmp/broken-home" bash "$broken/flow/install.sh" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "boom" \
   && [ -L "$tmp/broken-home/.claude/hooks/refresh-landed.sh" ] \
   && [ -L "$tmp/broken-home/.local/bin/job-run" ]; then
  echo "PASS a failing lane-install.sh reports loudly without half-installing the rest"
else
  echo "FAIL a failing lane-install.sh broke or silenced the rest of the install (rc=$rc): $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
