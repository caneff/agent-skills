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

# A scratch repo holding only what install.sh links, plus a stale pre-push hook
# left by an earlier install.
repo="$tmp/repo"
mkdir -p "$repo/tests"
cp -r "$root/flow" "$repo/flow"
rm -rf "$repo/flow/lane/target" # a build cache, not part of the source
cp "$root/tests/all.sh" "$repo/tests/all.sh"
git -C "$repo" init -q
ln -s "$repo/flow/../tests/all.sh" "$repo/.git/hooks/pre-push"
# backup-sync.sh --restore writes to absolute live paths (the Windows VS Code
# settings), not $HOME, so the scratch copy is a no-op.
printf '#!/usr/bin/env bash\nexit 0\n' > "$repo/flow/backup-sync.sh"

# An earlier install linked merge-cleanup to the bash script this repo no
# longer has; the install must replace that dangling link with the binary.
mkdir -p "$tmp/home/.local/bin"
ln -s "$repo/flow/bin/merge-cleanup" "$tmp/home/.local/bin/merge-cleanup"

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
mkdir -p "$empty/tests"
cp -r "$root/flow" "$empty/flow"
rm -rf "$empty/flow/lane/target"
cp "$root/tests/all.sh" "$empty/tests/all.sh"
git -C "$empty" init -q
rm -f "$empty/flow/claude/agents"/*.md
printf '#!/usr/bin/env bash\nexit 0\n' > "$empty/flow/backup-sync.sh"
if HOME="$empty/home" bash "$empty/flow/install.sh" >/dev/null 2>&1 \
   && [ -L "$empty/home/.claude/hooks/refresh-landed.sh" ]; then
  echo "PASS an empty claude/agents dir does not abort the install"
else
  echo "FAIL an empty claude/agents dir aborted the install"; fails=1
fi

# A failing lane-install.sh (a missing cargo, a compile error) runs last and
# must not half-install everything else — it was never a gate on the rest of
# install.sh before #748, and still is not.
broken="$tmp/broken"
mkdir -p "$broken/tests"
cp -r "$root/flow" "$broken/flow"
rm -rf "$broken/flow/lane/target"
cp "$root/tests/all.sh" "$broken/tests/all.sh"
git -C "$broken" init -q
printf '#!/usr/bin/env bash\nexit 0\n' > "$broken/flow/backup-sync.sh"
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
