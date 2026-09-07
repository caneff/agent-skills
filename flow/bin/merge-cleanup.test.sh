#!/usr/bin/env bash
# Contract test for merge-cleanup, against scratch origins and clones under
# mktemp. `gh` and `orca-ide` are stubbed on PATH and HOME is redirected, so
# nothing live — no real repo, no Orca workspace, no network — is touched.
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
# Three PATHs, so the gh-absent and orca-absent branches are reachable:
#   full  = gh + orca-ide + the real tools the script calls
#   nogh  = orca-ide only
#   noorca= gh only
mkbin() { # mkbin <dir> <stub>...
  local d="$1"; shift; mkdir -p "$d"
  local t; for t in bash git sed awk basename column; do
    local p; p=$(command -v "$t") && ln -sf "$p" "$d/$t"
  done
  local s; for s in "$@"; do ln -sf "$tmp/stubs/$s" "$d/$s"; done
}
mkdir -p "$tmp/stubs"
cat > "$tmp/stubs/gh" <<'STUB'
#!/usr/bin/env bash
# `pr list --head <b>` reports merged only for caneff/merged-one;
# `pr view <n>` resolves PR 7 to that same branch.
head=""; prev=""; sub="${1:-} ${2:-}"
for a in "$@"; do [ "$prev" = "--head" ] && head="$a"; prev="$a"; done
case "$sub" in
  "pr view") [ "${3:-}" = "7" ] && { echo caneff/merged-one; exit 0; }; exit 1 ;;
esac
if [ "$head" = "caneff/merged-one" ]; then echo '[{"number":7}]'; else echo '[]'; fi
STUB
cat > "$tmp/stubs/orca-ide" <<'STUB'
#!/usr/bin/env bash
echo "orca-ide $*" >> "$ORCA_LOG"
STUB
chmod +x "$tmp/stubs/gh" "$tmp/stubs/orca-ide"
mkbin "$tmp/full"   gh orca-ide
mkbin "$tmp/nogh"   orca-ide
mkbin "$tmp/noorca" gh
export ORCA_LOG="$tmp/orca.log"; : > "$ORCA_LOG"

# --- fixture ---------------------------------------------------------------
# A scratch origin plus a clone: caneff/merged-one is squash-merged (its own
# commits never reach main), caneff/ff-merged is a real fast-forward merge, and
# caneff/open-one is still open.
mkfixture() { # mkfixture <dir>
  local d="$1" origin="$1.origin.git"
  git init -q -b main --bare "$origin"
  git clone -q "$origin" "$d" 2>/dev/null
  git -C "$d" checkout -q -b main
  git -C "$d" config user.email t@example.com; git -C "$d" config user.name t
  echo one > "$d/f"; git -C "$d" add f; git -C "$d" commit -qm one
  git -C "$d" push -q -u origin main
  local b
  for b in caneff/merged-one caneff/open-one; do
    git -C "$d" checkout -q -b "$b" main
    echo "$b" >> "$d/f"; git -C "$d" commit -qam "$b"; git -C "$d" push -q -u origin "$b"
  done
  git -C "$d" checkout -q main
  # caneff/ff-merged is genuinely in main: `git branch -d` accepts it.
  git -C "$d" checkout -q -b caneff/ff-merged main
  echo ff >> "$d/f"; git -C "$d" commit -qam ff; git -C "$d" push -q -u origin caneff/ff-merged
  git -C "$d" checkout -q main; git -C "$d" merge -q --ff-only caneff/ff-merged
  # Never pushed and never merged: `git branch -d` refuses it, so it is the
  # only branch that exercises the -D fallback.
  git -C "$d" checkout -q -b caneff/local-only main
  echo local >> "$d/f"; git -C "$d" commit -qam local
  git -C "$d" checkout -q main
  # origin/main then moves ahead again (the squash of caneff/merged-one) while
  # the local main stays behind, so step 6 has something to fast-forward.
  echo squashed >> "$d/f"; git -C "$d" commit -qam "squash of caneff/merged-one"
  git -C "$d" push -q origin main
  git -C "$d" reset -q --hard HEAD~1
}
mc() { local p="$1"; shift; PATH="$p" bash "$here/merge-cleanup" "$@" 2>&1; }

# --- 1. dry run changes nothing -------------------------------------------
mkfixture "$tmp/r1"
before=$(git -C "$tmp/r1" rev-parse HEAD)
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/merged-one --dry-run); rc=$?
[ $rc -eq 0 ] || no "dry-run exited $rc: $out"
if git -C "$tmp/r1" show-ref -q --verify refs/heads/caneff/merged-one \
   && [ "$(git -C "$tmp/r1" rev-parse HEAD)" = "$before" ] \
   && [ ! -s "$ORCA_LOG" ]; then
  ok "dry-run leaves branch, HEAD and Orca untouched"
else
  no "dry-run mutated something"
fi

# --- 2. an unmerged branch is refused, --force overrides -------------------
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/open-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -qi "not merged" \
   && git -C "$tmp/r1" show-ref -q --verify refs/heads/caneff/open-one; then
  ok "unmerged branch refused, branch kept"
else
  no "unmerged branch not refused (rc=$rc): $out"
fi
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/open-one --force); rc=$?
if [ $rc -eq 0 ] && ! git -C "$tmp/r1" show-ref -q --verify refs/heads/caneff/open-one; then
  ok "--force cleans up an unmerged branch"
else
  no "--force did not clean up (rc=$rc): $out"
fi

# --- 3. the default branch is refused --------------------------------------
out=$(mc "$tmp/full" --repo "$tmp/r1" main); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "default branch" \
   && git -C "$tmp/r1" show-ref -q --verify refs/heads/main; then
  ok "default branch refused"
else
  no "default branch not refused (rc=$rc): $out"
fi

# --- 4. a real merge is deleted with -d, not -D ----------------------------
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/ff-merged); rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "deleted local branch caneff/ff-merged" \
   && ! printf '%s' "$out" | grep -q -- "-D"; then
  ok "a fast-forward merge is deleted with -d"
else
  no "-d path not taken (rc=$rc): $out"
fi

# --- 5. the full run: workspace, branches, fast-forward, skip lines --------
: > "$ORCA_LOG"
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/merged-one); rc=$?
[ $rc -eq 0 ] || no "cleanup exited $rc: $out"
grep -q -- "worktree rm .*caneff/merged-one" "$ORCA_LOG" \
  && ok "Orca workspace removed by full branch name" \
  || no "no orca-ide worktree rm for the full branch name: $(cat "$ORCA_LOG")"
git -C "$tmp/r1" show-ref -q --verify refs/heads/caneff/merged-one \
  && no "local branch survived" || ok "local branch deleted"
git -C "$tmp/r1.origin.git" show-ref -q --verify refs/heads/caneff/merged-one \
  && no "remote branch survived" || ok "remote branch deleted"
[ "$(git -C "$tmp/r1" rev-parse main)" = "$(git -C "$tmp/r1" rev-parse origin/main)" ] \
  && ok "primary checkout fast-forwarded" || no "main not fast-forwarded"
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/merged-one --force); rc=$?
printf '%s' "$out" | grep -q "skipped the local branch delete (no local caneff/merged-one)" \
  && ok "a skipped action says why" || no "no skip line for the missing branch: $out"

# A branch git itself calls unmerged falls back to -D.
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/local-only --force); rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q -- "with -D" \
   && ! git -C "$tmp/r1" show-ref -q --verify refs/heads/caneff/local-only; then
  ok "an unmerged branch falls back to -D"
else
  no "the -D fallback did not fire (rc=$rc): $out"
fi

# --- 6. --pr and a PR URL resolve to the head branch -----------------------
mkfixture "$tmp/r2"
out=$(mc "$tmp/full" --repo "$tmp/r2" --pr 7); rc=$?
if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q "PR #7 is caneff/merged-one" \
   && ! git -C "$tmp/r2" show-ref -q --verify refs/heads/caneff/merged-one; then
  ok "--pr resolves to the head branch"
else
  no "--pr did not resolve (rc=$rc): $out"
fi
mkfixture "$tmp/r3"
out=$(mc "$tmp/full" --repo "$tmp/r3" https://github.com/caneff/agent-skills/pull/7); rc=$?
if [ $rc -eq 0 ] && ! git -C "$tmp/r3" show-ref -q --verify refs/heads/caneff/merged-one; then
  ok "a PR URL resolves to the head branch"
else
  no "PR URL did not resolve (rc=$rc): $out"
fi

# --- 7. without gh, the ancestor test decides ------------------------------
mkfixture "$tmp/r4"
out=$(mc "$tmp/nogh" --repo "$tmp/r4" caneff/ff-merged); rc=$?
if [ $rc -eq 0 ] && ! git -C "$tmp/r4" show-ref -q --verify refs/heads/caneff/ff-merged; then
  ok "no gh: an ancestor branch is cleaned up"
else
  no "no-gh ancestor branch not cleaned (rc=$rc): $out"
fi
out=$(mc "$tmp/nogh" --repo "$tmp/r4" caneff/merged-one); rc=$?
if [ $rc -ne 0 ] && git -C "$tmp/r4" show-ref -q --verify refs/heads/caneff/merged-one; then
  ok "no gh: a squash-merged branch is refused, not guessed"
else
  no "no-gh squash branch not refused (rc=$rc): $out"
fi

# --- 8. without Orca, a linked worktree is removed anyway ------------------
mkfixture "$tmp/r5"
git -C "$tmp/r5" worktree add -q "$tmp/r5-wt" caneff/merged-one 2>/dev/null
out=$(mc "$tmp/noorca" --repo "$tmp/r5" caneff/merged-one); rc=$?
if [ $rc -eq 0 ] && ! git -C "$tmp/r5" show-ref -q --verify refs/heads/caneff/merged-one \
   && [ ! -d "$tmp/r5-wt" ]; then
  ok "no Orca: the linked worktree is removed and the branch deleted"
else
  no "linked worktree blocked the delete (rc=$rc): $out"
fi
printf '%s' "$out" | grep -q "skipped the Orca workspace teardown" \
  && ok "the missing orca-ide is reported as a skip" || no "no skip line for orca-ide: $out"

# --- 9. sweep: cleans the merged branch, spares the repo it cannot prove ----
mkdir -p "$tmp/src"
mkfixture "$tmp/src/other"
# A repo with no origin: nothing can prove its branch merged, so it survives.
git init -q -b main "$tmp/src/noremote"
git -C "$tmp/src/noremote" config user.email t@example.com
git -C "$tmp/src/noremote" config user.name t
echo x > "$tmp/src/noremote/f"; git -C "$tmp/src/noremote" add f
git -C "$tmp/src/noremote" commit -qm x
git -C "$tmp/src/noremote" branch caneff/untracked
: > "$ORCA_LOG"
out=$(mc "$tmp/full" --sweep --root "$tmp/src"); rc=$?
[ $rc -eq 0 ] || no "sweep exited $rc: $out"
git -C "$tmp/src/other" show-ref -q --verify refs/heads/caneff/merged-one \
  && no "sweep left a merged branch behind" || ok "sweep deleted the merged branch"
if git -C "$tmp/src/noremote" show-ref -q --verify refs/heads/caneff/untracked \
   && ! printf '%s' "$out" | grep -q "noremote caneff/untracked"; then
  ok "sweep spared the branch it could not prove merged, and never opened it"
else
  no "sweep did not skip the unprovable branch: $out"
fi
printf '%s' "$out" | grep -q "Orca worktrees removed: 2" \
  && ok "sweep summary counts the Orca worktrees removed" \
  || no "no Orca count in the sweep summary: $out"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
