#!/usr/bin/env bash
# Contract test for merge-cleanup, against a scratch origin + clone under
# mktemp. `gh` and `orca-ide` are stubbed on PATH, so nothing live — no real
# repo, no Orca workspace, no network — is touched.
# Run: bash flow/bin/merge-cleanup.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
export HOME="$tmp/home"; mkdir -p "$HOME"
fails=0
ok() { echo "PASS $1"; }
no() { echo "FAIL $1"; fails=1; }

# --- stubs -----------------------------------------------------------------
bin="$tmp/bin"; mkdir -p "$bin"
cat > "$bin/gh" <<'STUB'
#!/usr/bin/env bash
# `gh pr list --head <branch> ...` reports merged only for caneff/merged-one.
for a in "$@"; do [ "$prev" = "--head" ] && head="$a"; prev="$a"; done 2>/dev/null
head=""; prev=""
for a in "$@"; do [ "$prev" = "--head" ] && head="$a"; prev="$a"; done
if [ "$head" = "caneff/merged-one" ]; then echo '[{"number":7}]'; else echo '[]'; fi
STUB
cat > "$bin/orca-ide" <<'STUB'
#!/usr/bin/env bash
echo "orca-ide $*" >> "$ORCA_LOG"
STUB
chmod +x "$bin/gh" "$bin/orca-ide"
export ORCA_LOG="$tmp/orca.log"; : > "$ORCA_LOG"
export PATH="$bin:$PATH"

# --- scratch origin + clone ------------------------------------------------
git init -q -b main --bare "$tmp/origin.git"
git clone -q "$tmp/origin.git" "$tmp/repo" 2>/dev/null
cd "$tmp/repo"
git checkout -q -b main
git config user.email t@example.com; git config user.name t
echo one > f; git add f; git commit -qm one; git push -q -u origin main
for b in caneff/merged-one caneff/open-one; do
  git checkout -q -b "$b" main; echo "$b" >> f; git commit -qam "$b"; git push -q -u origin "$b"
done
git checkout -q main
# origin/main moves ahead (the squash merge), local main stays behind.
echo squashed >> f; git commit -qam "squash of caneff/merged-one"; git push -q origin main
git reset -q --hard HEAD~1
before_head=$(git rev-parse HEAD)

run() { PATH="$bin:$PATH" bash "$here/merge-cleanup" "$@" 2>&1; }

# --- 1. dry run changes nothing -------------------------------------------
out=$(run --repo "$tmp/repo" caneff/merged-one --dry-run); rc=$?
[ $rc -eq 0 ] || no "dry-run exited $rc: $out"
if git -C "$tmp/repo" show-ref -q --verify "refs/heads/caneff/merged-one" \
   && [ "$(git -C "$tmp/repo" rev-parse HEAD)" = "$before_head" ] \
   && [ ! -s "$ORCA_LOG" ]; then
  ok "dry-run leaves branch, HEAD and Orca untouched"
else
  no "dry-run mutated something"
fi

# --- 2. an unmerged branch is refused --------------------------------------
out=$(run --repo "$tmp/repo" caneff/open-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi "not merged" \
   && git -C "$tmp/repo" show-ref -q --verify "refs/heads/caneff/open-one"; then
  ok "unmerged branch refused, branch kept"
else
  no "unmerged branch not refused (rc=$rc): $out"
fi

# --- 3. the real run: workspace, branches, fast-forward ---------------------
out=$(run --repo "$tmp/repo" caneff/merged-one); rc=$?
[ $rc -eq 0 ] || no "cleanup exited $rc: $out"
grep -q -- "worktree rm .*caneff/merged-one" "$ORCA_LOG" \
  && ok "Orca workspace removed by full branch name" \
  || no "no orca-ide worktree rm for the full branch name: $(cat "$ORCA_LOG")"
git -C "$tmp/repo" show-ref -q --verify "refs/heads/caneff/merged-one" \
  && no "local branch survived" || ok "local branch deleted"
git -C "$tmp/origin.git" show-ref -q --verify "refs/heads/caneff/merged-one" \
  && no "remote branch survived" || ok "remote branch deleted"
[ "$(git -C "$tmp/repo" rev-parse main)" = "$(git -C "$tmp/repo" rev-parse origin/main)" ] \
  && ok "primary checkout fast-forwarded" || no "main not fast-forwarded"

# --- 4. sweep visits every repo under the root -----------------------------
git clone -q "$tmp/origin.git" "$tmp/src/other"
git -C "$tmp/src/other" config user.email t@example.com
git -C "$tmp/src/other" config user.name t
git -C "$tmp/src/other" checkout -q -b caneff/merged-one origin/main
mkdir -p "$tmp/src/notarepo"
out=$(run --sweep --root "$tmp/src"); rc=$?
[ $rc -eq 0 ] || no "sweep exited $rc: $out"
git -C "$tmp/src/other" show-ref -q --verify "refs/heads/caneff/merged-one" \
  && no "sweep left a merged branch behind" || ok "sweep deleted the merged branch"
printf '%s' "$out" | grep -q "notarepo" \
  && no "sweep tried to clean a non-repo" || ok "sweep skipped the non-repo"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
