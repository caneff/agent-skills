#!/usr/bin/env bash
# Contract test for merge-cleanup, against scratch origins and clones under
# mktemp. `gh` and `herdr` are stubbed on PATH and HOME is redirected, so
# nothing live — no real repo, no herdr pane, no session registry, no network —
# is touched.
# Run: bash flow/bin/merge-cleanup.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
export HOME="$tmp/home"; mkdir -p "$HOME"
fails=0
ok() { echo "PASS $1"; }
no() { echo "FAIL $1"; fails=1; }

# --- stubs -----------------------------------------------------------------
# Three PATHs, so the gh-absent and herdr-absent branches are reachable:
#   full   = gh + herdr + the real tools the script calls
#   nogh   = herdr only
#   noherdr= gh only
mkbin() { # mkbin <dir> <stub>...
  local d="$1"; shift; mkdir -p "$d"
  local t; for t in bash git sed awk basename column jq cat; do
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
# herdr answers `agent list` and `workspace list` from the JSON files the case
# under test writes, and logs every call.
cat > "$tmp/stubs/herdr" <<'STUB'
#!/usr/bin/env bash
echo "herdr $*" >> "$HERDR_LOG"
[ -n "${HERDR_FAIL:-}" ] && exit 1
case "${1:-} ${2:-}" in
  "agent list")     cat "$HERDR_AGENTS" ;;
  "workspace list") cat "$HERDR_WORKSPACES" ;;
esac
STUB
chmod +x "$tmp/stubs/gh" "$tmp/stubs/herdr"
mkbin "$tmp/full"    gh herdr
mkbin "$tmp/nogh"    herdr
mkbin "$tmp/noherdr" gh
mkbin "$tmp/nojq"    gh; rm "$tmp/nojq/jq"
export HERDR_LOG="$tmp/herdr.log"; : > "$HERDR_LOG"
export HERDR_AGENTS="$tmp/agents.json" HERDR_WORKSPACES="$tmp/workspaces.json"
echo '{"result":{"agents":[]}}' > "$HERDR_AGENTS"
echo '{"result":{"workspaces":[]}}' > "$HERDR_WORKSPACES"

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
   && ! grep -q "workspace close" "$HERDR_LOG"; then
  ok "dry-run leaves branch, HEAD and herdr untouched"
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
out=$(mc "$tmp/full" --repo "$tmp/r1" caneff/merged-one); rc=$?
[ $rc -eq 0 ] || no "cleanup exited $rc: $out"
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

# --- 8. without herdr, a linked worktree is removed anyway -----------------
mkfixture "$tmp/r5"
git -C "$tmp/r5" worktree add -q "$tmp/r5-wt" caneff/merged-one 2>/dev/null
out=$(mc "$tmp/noherdr" --repo "$tmp/r5" caneff/merged-one); rc=$?
if [ $rc -eq 0 ] && ! git -C "$tmp/r5" show-ref -q --verify refs/heads/caneff/merged-one \
   && [ ! -d "$tmp/r5-wt" ]; then
  ok "no herdr: the linked worktree is removed and the branch deleted"
else
  no "linked worktree blocked the delete (rc=$rc): $out"
fi
printf '%s' "$out" | grep -q "skipped the herdr workspace close (herdr is not on PATH)" \
  && ok "the missing herdr is reported as a skip" || no "no skip line for herdr: $out"

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
git -C "$tmp/src/other" worktree add -q --detach "$tmp/src/other/.claude/worktrees/agent-old" origin/main 2>/dev/null
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
if printf '%s\n' "$out" | sed -n '/stale, not removed/,$p' | grep -q "$tmp/src/other/.claude/worktrees/agent-old" \
   && [ -d "$tmp/src/other/.claude/worktrees/agent-old" ]; then
  ok "sweep summary lists the stale sibling and leaves it in place"
else
  no "sweep summary has no stale sibling: $out"
fi

# --- 10. the live-session guard --------------------------------------------
# A workspace at the lane's own path, holding the merged branch.
mkfixture "$tmp/r6"
wt6="$tmp/r6/.claude/worktrees/implement-1"
git -C "$tmp/r6" worktree add -q "$wt6" caneff/merged-one 2>/dev/null
mkdir -p "$HOME/.claude/sessions"
printf '{"pid":%s,"cwd":"%s"}\n' "$$" "$wt6" > "$HOME/.claude/sessions/live.json"
out=$(mc "$tmp/full" --repo "$tmp/r6" caneff/merged-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "pid $$" && [ -d "$wt6" ] \
   && git -C "$tmp/r6" show-ref -q --verify refs/heads/caneff/merged-one; then
  ok "a live registry pid in the workspace refuses the cleanup"
else
  no "live registry pid not refused (rc=$rc): $out"
fi
rm "$HOME/.claude/sessions/live.json"

printf '{"result":{"agents":[{"name":"skills-1","pane_id":"w2:p1","cwd":"%s"}]}}\n' "$wt6" > "$HERDR_AGENTS"
out=$(mc "$tmp/full" --repo "$tmp/r6" caneff/merged-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "skills-1" && [ -d "$wt6" ]; then
  ok "a herdr agent in the workspace refuses the cleanup"
else
  no "herdr agent not refused (rc=$rc): $out"
fi
echo '{"result":{"agents":[]}}' > "$HERDR_AGENTS"

out=$(HERDR_FAIL=1 mc "$tmp/full" --repo "$tmp/r6" caneff/merged-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "herdr agent list failed" && [ -d "$wt6" ]; then
  ok "a herdr that cannot list its agents refuses the cleanup"
else
  no "failing herdr agent list not refused (rc=$rc): $out"
fi
out=$(mc "$tmp/nojq" --repo "$tmp/r6" caneff/merged-one); rc=$?
if [ $rc -ne 0 ] && printf '%s' "$out" | grep -q "jq" && [ -d "$wt6" ]; then
  ok "without jq the registry cannot be read, so the cleanup is refused"
else
  no "missing jq not refused (rc=$rc): $out"
fi

# Siblings: one idle leftover, one with work ahead of main, one with a session.
wts="$tmp/r6/.claude/worktrees"
git -C "$tmp/r6" worktree add -q --detach "$wts/agent-old" origin/main 2>/dev/null
git -C "$tmp/r6" worktree add -q -b ahead "$wts/agent-ahead" origin/main 2>/dev/null
echo ahead >> "$wts/agent-ahead/f"; git -C "$wts/agent-ahead" commit -qam ahead
git -C "$tmp/r6" worktree add -q --detach "$wts/agent-live" origin/main 2>/dev/null
git -C "$tmp/r6" worktree add -q --detach "$wts/agent-dirty" origin/main 2>/dev/null
echo unsaved > "$wts/agent-dirty/notes"
printf '{"pid":%s,"cwd":"%s"}\n' "$$" "$wts/agent-live" > "$HOME/.claude/sessions/sibling.json"
# A crashed session leaves its registry file behind; its pid is gone.
bash -c 'exit 0' & dead=$!; wait "$dead"
printf '{"pid":%s,"cwd":"%s"}\n' "$dead" "$wt6" > "$HOME/.claude/sessions/dead.json"
printf '{"result":{"workspaces":[{"workspace_id":"w1","worktree":{"checkout_path":"%s"}},{"workspace_id":"w9","worktree":{"checkout_path":"%s"}}]}}\n' \
  "$tmp/r6" "$wt6" > "$HERDR_WORKSPACES"
: > "$HERDR_LOG"
out=$(mc "$tmp/full" --repo "$tmp/r6" caneff/merged-one --dry-run); rc=$?
if [ $rc -eq 0 ] && [ -d "$wt6" ] && grep -q "workspace list" "$HERDR_LOG" \
   && ! grep -q "workspace close" "$HERDR_LOG"; then
  ok "dry-run finds the herdr workspace but does not close it"
else
  no "dry-run closed or never looked up the herdr workspace (rc=$rc): $(cat "$HERDR_LOG") / $out"
fi
: > "$HERDR_LOG"
out=$(mc "$tmp/full" --repo "$tmp/r6" caneff/merged-one); rc=$?
if [ $rc -eq 0 ] && [ ! -d "$wt6" ] \
   && ! git -C "$tmp/r6" show-ref -q --verify refs/heads/caneff/merged-one; then
  ok "a registry file with a dead pid does not block the cleanup"
else
  no "dead registry pid blocked the cleanup (rc=$rc): $out"
fi
if grep -qx "herdr workspace close w9" "$HERDR_LOG" && ! grep -q "close w1" "$HERDR_LOG" \
   && printf '%s\n' "$out" | awk '/removing the linked worktree/{r=NR} /closing herdr workspace w9/{c=NR; exit} END{exit !(r && c > r)}'; then
  ok "the matching herdr workspace is closed after the worktree is removed"
else
  no "herdr workspace close not called for w9 after removal: $(cat "$HERDR_LOG") / $out"
fi
stale=$(printf '%s\n' "$out" | sed -n '/stale, not removed/,$p')
if printf '%s' "$stale" | grep -q "$wts/agent-old" \
   && ! printf '%s' "$stale" | grep -qE "agent-ahead|agent-live|agent-dirty|implement-1" \
   && [ -d "$wts/agent-old" ] && [ -d "$wts/agent-ahead" ] && [ -d "$wts/agent-live" ]; then
  ok "an idle sibling worktree is listed as stale and left in place"
else
  no "stale sibling report wrong: $out"
fi
rm "$HOME/.claude/sessions/sibling.json" "$HOME/.claude/sessions/dead.json"

# A removal git refuses (a locked worktree) leaves the herdr workspace open.
mkfixture "$tmp/r7"
wt7="$tmp/r7/.claude/worktrees/implement-2"
git -C "$tmp/r7" worktree add -q "$wt7" caneff/merged-one 2>/dev/null
git -C "$tmp/r7" worktree lock "$wt7"
printf '{"result":{"workspaces":[{"workspace_id":"w5","worktree":{"checkout_path":"%s"}}]}}\n' "$wt7" > "$HERDR_WORKSPACES"
: > "$HERDR_LOG"
out=$(mc "$tmp/full" --repo "$tmp/r7" caneff/merged-one); rc=$?
if [ -d "$wt7" ] && ! grep -q "workspace close" "$HERDR_LOG"; then
  ok "a failed worktree removal does not close the herdr workspace"
else
  no "herdr workspace closed although the worktree survived (rc=$rc): $(cat "$HERDR_LOG") / $out"
fi
echo '{"result":{"workspaces":[]}}' > "$HERDR_WORKSPACES"

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
