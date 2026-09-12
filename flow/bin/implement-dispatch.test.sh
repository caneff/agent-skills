#!/usr/bin/env bash
# Contract test for implement-dispatch, against a scratch origin and clone under
# mktemp. `gh` and `herdr` are stubbed on PATH and log their argv; HOME is
# redirected with a fake ~/.claude.json, so nothing live — no real repo, no
# herdr pane, no claude session, no network — is touched.
# Run: bash flow/bin/implement-dispatch.test.sh
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
mkdir -p "$tmp/stubs" "$tmp/bin"
for t in bash git sed grep jq cat mv rm mktemp; do
  p=$(command -v "$t") && ln -sf "$p" "$tmp/bin/$t"
done
# gh: `issue view` answers the state in $GH_STATE (empty = no such issue).
cat > "$tmp/stubs/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "$CALL_LOG"
case "${1:-} ${2:-}" in
  "issue view") [ -n "$GH_STATE" ] || { echo "no issue" >&2; exit 1; }; echo "$GH_STATE" ;;
esac
STUB
# herdr: `status --json` reports $HERDR_RUNNING; `worktree open` returns a root
# pane unless $HERDR_NO_ROOT_PANE, in which case `pane list` names it; `agent
# prompt` stalls when $HERDR_STALL is set.
cat > "$tmp/stubs/herdr" <<'STUB'
#!/usr/bin/env bash
echo "herdr $*" >> "$CALL_LOG"
case "${1:-} ${2:-}" in
  "status --json") echo "{\"server\":{\"running\":$HERDR_RUNNING}}" ;;
  "worktree open")
    if [ -n "${HERDR_NO_ROOT_PANE:-}" ]; then echo '{"result":{"workspace":{"workspace_id":"w8"}}}'
    else echo '{"result":{"workspace":{"workspace_id":"w7"},"root_pane":{"pane_id":"w7:p1"}}}'; fi ;;
  "pane list") echo '{"result":{"panes":[{"pane_id":"w8:p3"}]}}' ;;
  "agent prompt")
    [ -n "${HERDR_STALL:-}" ] || exit 0
    echo '{"error":{"code":"agent_prompt_stalled","message":"no activity observed"},"id":"cli:agent:prompt"}'
    exit 1 ;;
esac
STUB
chmod +x "$tmp/stubs/gh" "$tmp/stubs/herdr"
ln -sf "$tmp/stubs/gh" "$tmp/bin/gh"; ln -sf "$tmp/stubs/herdr" "$tmp/bin/herdr"
export CALL_LOG="$tmp/calls.log" GH_STATE=OPEN HERDR_RUNNING=true

# --- fixture ---------------------------------------------------------------
# A scratch origin plus a clone with no origin/HEAD, whose origin/main is one
# commit ahead of the local main: the base must be origin/main, not HEAD.
mkfixture() { # mkfixture <dir>
  local d="$1" origin="$1.origin.git"
  git init -q -b main --bare "$origin"
  git clone -q "$origin" "$d" 2>/dev/null
  git -C "$d" checkout -q -b main
  git -C "$d" config user.email t@example.com; git -C "$d" config user.name t
  echo one > "$d/f"; git -C "$d" add f; git -C "$d" commit -qm one
  echo two >> "$d/f"; git -C "$d" commit -qam two
  git -C "$d" push -q -u origin main
  git -C "$d" reset -q --hard HEAD~1
}
reset_home() { # onboarding true, one pre-existing project entry
  printf '{"hasCompletedOnboarding":%s,"projects":{"/elsewhere":{"hasTrustDialogAccepted":false}}}\n' \
    "${1:-true}" > "$HOME/.claude.json"
  : > "$CALL_LOG"
}
dispatch() { PATH="$tmp/bin" bash "$here/implement-dispatch" "$@" 2>&1; }
refused() { # refused <label> <rc> <out> <repo> <n> <expect-text>
  local label="$1" rc="$2" out="$3" repo="$4" n="$5" want="$6"
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -qi -- "$want" \
     && ! grep -q "worktree open\|issue edit" "$CALL_LOG" \
     && ! git -C "$repo" show-ref -q --verify "refs/heads/implement-$n"; then
    ok "$label"
  else
    no "$label (rc=$rc): $out / $(cat "$CALL_LOG")"
  fi
}

repo="$tmp/sudokumaker-custom-constraints"
mkfixture "$repo"

# --- 1. refusals: nothing is claimed, created or opened --------------------
reset_home
out=$(HERDR_RUNNING=false dispatch --repo "$repo" 395); rc=$?
refused "refuses when no herdr server is running" "$rc" "$out" "$repo" 395 "herdr server"

reset_home false
out=$(dispatch --repo "$repo" 395); rc=$?
refused "refuses when claude onboarding is not complete" "$rc" "$out" "$repo" 395 "onboarding"

reset_home
out=$(GH_STATE=CLOSED dispatch --repo "$repo" 395); rc=$?
refused "refuses a closed issue" "$rc" "$out" "$repo" 395 "not an open issue"
reset_home
out=$(GH_STATE="" dispatch --repo "$repo" 395); rc=$?
refused "refuses a missing issue" "$rc" "$out" "$repo" 395 "not an open issue"

reset_home
mkdir -p "$repo/.claude/worktrees/implement-395"
out=$(dispatch --repo "$repo" 395); rc=$?
refused "refuses when the workspace path exists" "$rc" "$out" "$repo" 395 "already exists"
rmdir "$repo/.claude/worktrees/implement-395"

reset_home
git -C "$repo" branch implement-396 main
out=$(dispatch --repo "$repo" 396); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "already exists" \
   && [ ! -e "$repo/.claude/worktrees/implement-396" ] && ! grep -q "worktree open\|issue edit" "$CALL_LOG"; then
  ok "refuses when the branch exists"
else
  no "existing branch not refused (rc=$rc): $out"
fi

# --- 2. the full dispatch ---------------------------------------------------
reset_home
git -C "$repo" symbolic-ref -q refs/remotes/origin/HEAD && no "fixture unexpectedly has origin/HEAD"
wt="$repo/.claude/worktrees/implement-395"
out=$(dispatch --repo "$repo" 395); rc=$?
[ "$rc" -eq 0 ] || no "dispatch exited $rc: $out"
if [ "$(git -C "$wt" branch --show-current 2>/dev/null)" = implement-395 ] \
   && [ "$(git -C "$wt" rev-parse HEAD)" = "$(git -C "$repo" rev-parse origin/main)" ]; then
  ok "creates the workspace and branch off origin/main with no origin/HEAD"
else
  no "workspace or base wrong: $out"
fi
if [ "$(jq -c --arg p "$wt" '[.projects | keys[]] == ["/elsewhere", $p] and .projects[$p].hasTrustDialogAccepted == true and .projects["/elsewhere"].hasTrustDialogAccepted == false and .hasCompletedOnboarding == true' "$HOME/.claude.json")" = true ]; then
  ok "writes the trust key for exactly the new path"
else
  no "trust key wrong: $(cat "$HOME/.claude.json")"
fi
# herdr allows 1-32 characters; the repo part is cut so the whole is exactly 32.
name=sudokumaker-custom-constrain-395
herdr_calls=$(grep '^herdr \(worktree\|agent\)' "$CALL_LOG")
expected="herdr worktree open --cwd $repo --path $wt --label implement-395 --no-focus --trust-repository
herdr agent start $name --kind claude --pane w7:p1 -- --model sonnet
herdr agent prompt $name /implement 395 --wait --until working --timeout 120000"
if [ "$herdr_calls" = "$expected" ]; then
  ok "calls open, start, prompt in order with the truncated agent name"
else
  no "herdr calls wrong:
$herdr_calls"
fi
grep -q "^gh issue edit 395 --remove-label ready-for-agent --add-label in-progress --add-assignee @me" "$CALL_LOG" \
  && ok "claims the ticket" || no "ticket not claimed: $(cat "$CALL_LOG")"
if printf '%s' "$out" | grep -q "worktree: $wt" && printf '%s' "$out" | grep -q "branch: *implement-395" \
   && printf '%s' "$out" | grep -q "agent: *$name" \
   && printf '%s' "$out" | grep -qF "cd $repo && merge-cleanup implement-395 --repo $repo"; then
  ok "the report names path, branch, agent and the cleanup line"
else
  no "report incomplete: $out"
fi

# --- 3. --model, and a worktree open that returns no root pane -------------
reset_home
out=$(HERDR_NO_ROOT_PANE=1 dispatch --repo "$repo" --model opus 397); rc=$?
if [ "$rc" -eq 0 ] && grep -qx "herdr agent start sudokumaker-custom-constrain-397 --kind claude --pane w8:p3 -- --model opus" "$CALL_LOG"; then
  ok "--model reaches agent start; the pane comes from pane list when open names none"
else
  no "--model or pane fallback wrong (rc=$rc): $out / $(cat "$CALL_LOG")"
fi
reset_home
out=$(dispatch --repo "$repo" --model haiku 398); rc=$?
refused "refuses a model other than sonnet or opus" "$rc" "$out" "$repo" 398 "model"
reset_home
out=$(timeout 10 env PATH="$tmp/bin" bash "$here/implement-dispatch" 398 --model 2>&1); rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] && printf '%s' "$out" | grep -q -- "--model needs a value"; then
  ok "a flag with no value is refused, not looped on"
else
  no "a trailing --model hung or was accepted (rc=$rc): $out"
fi

# --- 4. a stalled prompt fails and leaves the workspace ---------------------
reset_home
out=$(HERDR_STALL=1 dispatch --repo "$repo" 399); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q agent_prompt_stalled \
   && [ -d "$repo/.claude/worktrees/implement-399" ]; then
  ok "a stalled prompt exits non-zero with herdr's error and leaves the worktree"
else
  no "stall not reported (rc=$rc): $out"
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
