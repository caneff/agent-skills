#!/usr/bin/env bash
# Contract test for block-dangerous-git.sh: synthetic PreToolUse JSON on stdin
# -> exit 0 (allow) or exit 2 + message on stderr (block). Never pokes at the
# hook's internals. `gh` is stubbed via PATH so this runs offline.
# Run: bash flow/claude/hooks/block-dangerous-git.test.sh
set -uo pipefail
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would redirect the
# repo init below at that caller's repo instead of $tmp (#620).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/block-dangerous-git.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export XDG_CACHE_HOME="$tmp/cache"   # keep the ownership cache out of the real one

# A throwaway repo with a github origin, sitting on its default branch.
repo="$tmp/repo"
git init -q -b main "$repo"
git -C "$repo" remote add origin https://github.com/caneff/agent-skills.git

# gh stub: `gh api user` prints $STUB_LOGIN, `gh repo view` prints $STUB_OWNER/name.
# Either being empty makes the stub exit non-zero, standing in for "gh broke".
stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "api user")  [ -n "${STUB_LOGIN:-}" ] || exit 1; printf '%s\n' "$STUB_LOGIN" ;;
  "repo view") [ -n "${STUB_OWNER:-}" ] || exit 1; printf '%s/agent-skills\n' "$STUB_OWNER" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stubdir/gh"

fails=0
# run <name> <expected-exit> <command-string> [<substring stderr must contain>]
run() {
  local name=$1 want=$2 cmd=$3 needle=${4:-}
  local out rc
  out=$(printf '%s' "$cmd" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
        | (cd "$repo" && PATH="$stubdir:$PATH" bash "$hook") 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL: $name — stderr missing '$needle'"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

# Owned repo (origin owner == gh login): a push of code to the default branch.
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "owned repo: push code to default branch allowed" 0 "git push origin main"
run "owned repo: force-with-lease allowed" 0 "git push --force-with-lease origin main"

# The owned verdict is cached, so gh going away afterwards costs nothing.
export STUB_LOGIN= STUB_OWNER=
run "cached owned verdict survives gh failing" 0 "git push origin main"

# Not owned: same push, different origin owner -> blocked, and the message
# hands the outward step back to the user rather than dead-ending.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=someone-else
run "unowned repo: push blocked, hands the user the line" 2 "git push origin main" "gh pr create"

# gh unavailable (errors / no network) -> fail closed, block.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN= STUB_OWNER=
run "ownership lookup failure blocks" 2 "git push origin main" "BLOCKED"

# Merging a PR follows ownership (#790): the controller merges on an owned
# repo, and every other repo's merge stays the user's.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "gh pr merge allowed on owned repo" 0 "gh pr merge 12 --repo caneff/agent-skills --squash"
run "gh pr merge allowed on owned repo, no --repo" 0 "gh pr merge 12 --squash"
run "gh pr merge naming someone else's repo blocked from an owned checkout" 2 \
  "gh pr merge 12 --repo someone-else/agent-skills --squash" "BLOCKED"
run "gh pr merge -R naming someone else's repo blocked" 2 \
  "gh pr merge 12 -R someone-else/agent-skills" "BLOCKED"
run "gh pr merge on someone else's PR URL blocked" 2 \
  "gh pr merge https://github.com/someone-else/agent-skills/pull/12 --squash" "BLOCKED"

rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=someone-else
run "gh pr merge blocked on unowned repo" 2 "gh pr merge 12 --squash" "gh pr merge"
run "gh pr merge later in a chain blocked on unowned repo" 2 \
  "git status && gh pr merge 12 --squash" "gh pr merge"
run "gh pr merge run by bash -c blocked on unowned repo" 2 \
  "bash -c 'gh pr merge 12 --squash'" "gh pr merge"
run "gh pr merge in a command substitution blocked on unowned repo" 2 \
  "echo \"\$(gh pr merge 12 --squash)\"" "gh pr merge"
# Only the command is guarded, not the phrase: reading or searching for it runs
# nothing (a read-only grep was blocked before #790).
run "grep for the phrase allowed on unowned repo" 0 "grep 'gh pr merge' flow/claude/CLAUDE.md"
run "phrase mid-sentence in a commit message allowed on unowned repo" 0 \
  "git commit -m \"docs: the controller runs gh pr merge after CLEAN\""
run "rg for the phrase in a substitution allowed on unowned repo" 0 \
  "n=\$(rg -c \"gh pr merge\" implement/SKILL.md)"

run "gh pr merge chained with no spaces blocked on unowned repo" 2 \
  "git status&&gh pr merge 12 --squash" "gh pr merge"
# A --repo naming an owned repo, on another command or in a quoted subject,
# never stands in for this checkout's ownership.
run "owned --repo on another command does not unlock an unowned checkout" 2 \
  "gh pr view 5 --repo caneff/agent-skills && gh pr merge 12" "gh pr merge"
run "an apostrophe in double quotes does not hide a later merge" 2 \
  "git commit -m \"don't\" && gh pr merge 12 && echo 'ok'" "gh pr merge"
run "gh pr merge in a heredoc fed to bash blocked on unowned repo" 2 \
  $'bash <<EOF\ngh pr merge 12 --squash\nEOF' "gh pr merge"
run "phrase search with a --type sh flag allowed on unowned repo" 0 \
  "rg \"gh pr merge 12\" --type sh"
run "a bash run chained with a phrase grep allowed on unowned repo" 0 \
  "bash tests/all.sh && grep -rn \"gh pr merge --squash\" ."
run "backticks inside single quotes allowed on unowned repo" 0 \
  "gh pr create --title t --body 'run \`gh pr merge 12\` after CLEAN'"
run "gh pr merge piped into a shell blocked on unowned repo" 2 \
  "echo 'gh pr merge 12' | sh" "gh pr merge"

rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "GH_REPO naming someone else's repo blocked from an owned checkout" 2 \
  "GH_REPO=someone-else/agent-skills gh pr merge 12" "BLOCKED"
# Owned verdict now cached; a named owner still needs the login to compare.
export STUB_LOGIN= STUB_OWNER=
run "named owner blocked when the login lookup fails" 2 \
  "gh pr merge 12 --repo caneff/agent-skills" "BLOCKED"

rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN= STUB_OWNER=
run "gh pr merge blocked when ownership lookup fails" 2 "gh pr merge 12 --squash" "BLOCKED"
export STUB_LOGIN=caneff STUB_OWNER=caneff

# Unrelated destructive guards survive the rework.
run "history destroyer still blocked" 2 "git reset --hard HEAD~3" "BLOCKED"
run "bare force-push still blocked" 2 "git push --force origin main" "BLOCKED"

# The rejection message must name the matched pattern generically — not lean
# on gh-pr-merge-specific wording for a different pattern — and state an
# escape hatch that is actually reachable: the hook blocks the protected
# pattern unconditionally, so "run it alone" is a dead end (it's blocked the
# same way). The real hatch is: drop the protected part, hand the user the
# exact "! <pattern> ..." line to run themselves.
run "history destroyer message names its own pattern, not gh pr merge" 2 \
  "git reset --hard HEAD~3" "protected pattern 'git reset --hard'"
run "history destroyer message tells the agent to drop the protected part" 2 \
  "git reset --hard HEAD~3" "re-run the command without it"
run "history destroyer message hands the user a runnable ! line" 2 \
  "git reset --hard HEAD~3" "! git reset --hard ..."

# A protected pattern anywhere in a compound chain still blocks the whole
# chain (whole-command matching, unchanged), and the message names the
# specific segment that tripped it.
run "chain blocked names the tripping segment's pattern" 2 \
  "ls -la && git branch -D foo" "protected pattern 'git branch -D'"

# The force-push guard is per segment: a `--force` that belongs to some other
# command in the chain, or a `push` that is only a word in a path, is not a
# force-push (#637 — three false blocks in one burn).
run "force on a non-push segment after a push allowed" 0 \
  "git push -q origin b; git worktree remove --force x"
run "pre-push path plus worktree remove --force allowed" 0 \
  "ls .git/hooks/pre-push && git worktree remove --force /tmp/x"
run "git -C push -f still blocked" 2 "git -C /r push -f origin main" "force-push"
run "force-push in a later segment still blocked" 2 \
  "git fetch && git push --force origin main" "force-push"

# Reading git is untouched.
run "ordinary git command allowed" 0 "git status"

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
