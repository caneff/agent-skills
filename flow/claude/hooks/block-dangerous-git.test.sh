#!/usr/bin/env bash
# Contract test for block-dangerous-git.sh: synthetic PreToolUse JSON on stdin
# -> exit 0 (allow) or exit 2 + message on stderr (block). Never pokes at the
# hook's internals. `gh` is stubbed via PATH so this runs offline.
# Run: bash flow/claude/hooks/block-dangerous-git.test.sh
set -uo pipefail
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

# Not owned: same push, different origin owner -> blocked, hand-off names pushpr.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=someone-else
run "unowned repo: push blocked, names pushpr" 2 "git push origin main" "pushpr"

# gh unavailable (errors / no network) -> fail closed, block.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN= STUB_OWNER=
run "ownership lookup failure blocks" 2 "git push origin main" "BLOCKED"

# Merging a PR is the user's, everywhere — owned repo included.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "gh pr merge blocked on owned repo" 2 "gh pr merge 12 --squash" "gh pr merge"

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

# Reading git is untouched.
run "ordinary git command allowed" 0 "git status"

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
