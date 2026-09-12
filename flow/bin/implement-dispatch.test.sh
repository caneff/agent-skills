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
for t in bash git sed grep cat mv rm mktemp flock; do
  p=$(command -v "$t") && ln -sf "$p" "$tmp/bin/$t"
done
# jq: the real one, except that the trust rewrite dawdles for a second when
# $JQ_SLOW is set, so two concurrent dispatches overlap inside it.
cat > "$tmp/bin/jq" <<STUB
#!/usr/bin/env bash
case "\$*" in *'hasTrustDialogAccepted = true'*) [ -n "\${JQ_SLOW:-}" ] && $(command -v sleep) 1 ;; esac
exec $(command -v jq) "\$@"
STUB
chmod +x "$tmp/bin/jq"
# gh: `issue view` answers "$GH_STATE $GH_LABELS" (empty state = no such issue).
cat > "$tmp/stubs/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "$CALL_LOG"
case "${1:-} ${2:-}" in
  "issue view") [ -n "$GH_STATE" ] || { echo "no issue" >&2; exit 1; }; echo "$GH_STATE $GH_LABELS" ;;
esac
STUB
# herdr: `status --json` reports $HERDR_RUNNING; `worktree open` returns a root
# pane unless $HERDR_NO_ROOT_PANE, in which case `pane list` names it; `agent
# get` finds an agent only when $HERDR_AGENT_TAKEN; `agent prompt` stalls when
# $HERDR_STALL is set.
cat > "$tmp/stubs/herdr" <<'STUB'
#!/usr/bin/env bash
echo "herdr $*" >> "$CALL_LOG"
case "${1:-} ${2:-}" in
  "status --json") echo "{\"server\":{\"running\":$HERDR_RUNNING}}" ;;
  "worktree open")
    if [ -n "${HERDR_NO_ROOT_PANE:-}" ]; then echo '{"result":{"workspace":{"workspace_id":"w8"}}}'
    else echo '{"result":{"workspace":{"workspace_id":"w7"},"root_pane":{"pane_id":"w7:p1"}}}'; fi ;;
  "agent get")
    [ -n "${HERDR_AGENT_TAKEN:-}" ] && { echo '{"result":{"agent":{"name":"taken"}}}'; exit 0; }
    echo '{"error":{"code":"agent_not_found","message":"not found"}}'; exit 1 ;;
  "pane list") echo '{"result":{"panes":[{"pane_id":"w8:p3"}]}}' ;;
  "agent prompt")
    [ -n "${HERDR_STALL:-}" ] || exit 0
    echo '{"error":{"code":"agent_prompt_stalled","message":"no activity observed"},"id":"cli:agent:prompt"}'
    exit 1 ;;
esac
STUB
chmod +x "$tmp/stubs/gh" "$tmp/stubs/herdr"
ln -sf "$tmp/stubs/gh" "$tmp/bin/gh"; ln -sf "$tmp/stubs/herdr" "$tmp/bin/herdr"
export CALL_LOG="$tmp/calls.log" GH_STATE=OPEN GH_LABELS=enhancement,ready-for-agent HERDR_RUNNING=true
# The controller: this test shell stands in for the dispatching Claude session,
# an ancestor of every dispatch it runs.
mkdir -p "$HOME/.claude/sessions"
session_file="$HOME/.claude/sessions/$$.json"
echo '{"pid":1,"name":"skills-ctl"}' > "$session_file"

# --- fixture ---------------------------------------------------------------
# A scratch origin plus a clone with no origin/HEAD, whose origin/<default> is
# one commit ahead of the local one: the base must be origin/<default>, not HEAD.
# The origin lives under a github.com/caneff/ path, so it names owner/name.
mkfixture() { # mkfixture <dir> [default branch]
  local d="$1" origin="$tmp/github.com/caneff/${1##*/}.git" b="${2:-main}"
  git init -q -b "$b" --bare "$origin"
  git clone -q "$origin" "$d" 2>/dev/null
  git -C "$d" checkout -q -b "$b"
  git -C "$d" config user.email t@example.com; git -C "$d" config user.name t
  echo one > "$d/f"; git -C "$d" add f; git -C "$d" commit -qm one
  echo two >> "$d/f"; git -C "$d" commit -qam two
  git -C "$d" push -q -u origin "$b"
  git -C "$d" reset -q --hard HEAD~1
}
reset_home() { # reset_home [onboarding] -> fresh ~/.claude.json with one other project, empty call log
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
nfix="$tmp/notgithub"
mkfixture "$nfix"
git -C "$nfix" remote set-url origin "$tmp/elsewhere/notgithub.git"
out=$(dispatch --repo "$nfix" 395); rc=$?
refused "refuses an origin that names no GitHub owner/name" "$rc" "$out" "$nfix" 395 "owner/name"
grep -q '^gh ' "$CALL_LOG" && no "gh was called without an owner/name: $(cat "$CALL_LOG")"
reset_home
mkdir -p "$tmp/noflock"; cp -P "$tmp/bin"/* "$tmp/noflock/"; rm "$tmp/noflock/flock"
out=$(PATH="$tmp/noflock" bash "$here/implement-dispatch" --repo "$repo" 395 2>&1); rc=$?
refused "refuses when flock is not on PATH" "$rc" "$out" "$repo" 395 "flock is not on PATH"
reset_home
out=$(GH_LABELS=in-progress dispatch --repo "$repo" 395); rc=$?
refused "refuses an issue not labelled ready-for-agent" "$rc" "$out" "$repo" 395 "ready-for-agent"
reset_home
out=$(GH_LABELS=ready-for-agent,in-progress dispatch --repo "$repo" 395); rc=$?
refused "refuses a ready-for-agent issue that is also held" "$rc" "$out" "$repo" 395 "in-progress"
reset_home
out=$(HERDR_AGENT_TAKEN=1 dispatch --repo "$repo" 395); rc=$?
refused "refuses when the herdr agent name is already taken" "$rc" "$out" "$repo" 395 "sudokumaker-custom-constrain-395"

reset_home
mkdir -p "$repo/.claude/worktrees/implement-395"
out=$(dispatch --repo "$repo" 395); rc=$?
refused "refuses when the workspace path exists" "$rc" "$out" "$repo" 395 "already exists"
rmdir "$repo/.claude/worktrees/implement-395"
# Registered with git, but its directory is gone.
reset_home
git -C "$repo" worktree add -q --detach "$repo/.claude/worktrees/implement-394" main 2>/dev/null
rm -rf "$repo/.claude/worktrees/implement-394"
out=$(dispatch --repo "$repo" 394); rc=$?
refused "refuses when git still registers a worktree at the path" "$rc" "$out" "$repo" 394 "already exists"
git -C "$repo" worktree prune

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
herdr_calls=$(grep '^herdr \(worktree open\|agent start\|agent prompt\)' "$CALL_LOG")
expected="herdr worktree open --cwd $repo --path $wt --label implement-395 --no-focus --trust-repository
herdr agent start $name --kind claude --pane w7:p1 -- --model sonnet
herdr agent prompt $name /implement 395 --tier heavy --controller skills-ctl --wait --until working --timeout 120000"
if [ "$herdr_calls" = "$expected" ]; then
  ok "calls open, start, prompt in order with the truncated agent name"
else
  no "herdr calls wrong:
$herdr_calls"
fi
if ! grep '^gh ' "$CALL_LOG" | grep -vq -- "--repo caneff/sudokumaker-custom-constraints"; then
  ok "every gh call names the repo from origin with --repo"
else
  no "a gh call relied on the cwd: $(grep '^gh ' "$CALL_LOG")"
fi
grep -q "^gh issue edit 395 --repo caneff/sudokumaker-custom-constraints --remove-label ready-for-agent --add-label in-progress --add-assignee @me" "$CALL_LOG" \
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

# --- 3b. tier from the documentation label; controller from flag or session ---
reset_home
out=$(GH_LABELS=documentation,ready-for-agent dispatch --repo "$repo" 403); rc=$?
if [ "$rc" -eq 0 ] && grep -qx "herdr agent prompt sudokumaker-custom-constrain-403 /implement 403 --tier light --controller skills-ctl --wait --until working --timeout 120000" "$CALL_LOG"; then
  ok "a documentation label puts --tier light in the brief"
else
  no "light tier missing (rc=$rc): $out / $(cat "$CALL_LOG")"
fi
reset_home
out=$(dispatch --repo "$repo" --controller other-9 404); rc=$?
if [ "$rc" -eq 0 ] && grep -qx "herdr agent prompt sudokumaker-custom-constrain-404 /implement 404 --tier heavy --controller other-9 --wait --until working --timeout 120000" "$CALL_LOG"; then
  ok "--controller overrides the session registry"
else
  no "--controller not in the brief (rc=$rc): $out / $(cat "$CALL_LOG")"
fi
reset_home
mv "$session_file" "$session_file.off"
out=$(dispatch --repo "$repo" 405); rc=$?
mv "$session_file.off" "$session_file"
refused "refuses when no controller session is found and none is named" "$rc" "$out" "$repo" 405 "controller"

# --- 4. the base follows the resolver: origin has only master, no origin/HEAD
reset_home
mfix="$tmp/masteronly"
mkfixture "$mfix" master
out=$(dispatch --repo "$mfix" 401); rc=$?
if [ "$rc" -eq 0 ] && [ "$(git -C "$mfix/.claude/worktrees/implement-401" rev-parse HEAD 2>/dev/null)" = "$(git -C "$mfix" rev-parse origin/master)" ]; then
  ok "the base is origin/master when origin has no main and no HEAD"
else
  no "master-only base wrong (rc=$rc): $out"
fi

# An origin with neither main nor master and no HEAD: no base, so nothing is claimed.
reset_home
tfix="$tmp/trunkonly"
mkfixture "$tfix" trunk
out=$(dispatch --repo "$tfix" 402); rc=$?
refused "refuses when the resolved base is not on origin" "$rc" "$out" "$tfix" 402 "origin/main"

# --- 5. a stalled prompt fails and leaves the workspace ---------------------
reset_home
out=$(HERDR_STALL=1 dispatch --repo "$repo" 399); rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q agent_prompt_stalled \
   && [ -d "$repo/.claude/worktrees/implement-399" ]; then
  ok "a stalled prompt exits non-zero with herdr's error and leaves the worktree"
else
  no "stall not reported (rc=$rc): $out"
fi

# --- 6. concurrent dispatches both keep their trust key ----------------------
reset_home
mkfixture "$tmp/race-a"; mkfixture "$tmp/race-b"
JQ_SLOW=1 dispatch --repo "$tmp/race-a" 501 > "$tmp/race-a.out" & pa=$!
JQ_SLOW=1 dispatch --repo "$tmp/race-b" 502 > "$tmp/race-b.out" & pb=$!
wait "$pa"; ra=$?; wait "$pb"; rb=$?
if [ "$ra" -eq 0 ] && [ "$rb" -eq 0 ] \
   && [ "$(jq --arg a "$tmp/race-a/.claude/worktrees/implement-501" --arg b "$tmp/race-b/.claude/worktrees/implement-502" \
         '.projects[$a].hasTrustDialogAccepted == true and .projects[$b].hasTrustDialogAccepted == true and .projects["/elsewhere"] != null' "$HOME/.claude.json")" = true ]; then
  ok "two concurrent dispatches both leave their trust keys"
else
  no "a concurrent dispatch lost a trust key (rc=$ra/$rb): $(cat "$HOME/.claude.json") / $(cat "$tmp/race-a.out" "$tmp/race-b.out")"
fi

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
