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
# The hook reads pushRemote, pushDefault and insteadOf, which git also takes
# from the global and system config: point both at this test's own files.
mkdir -p "$tmp/home"
export HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" GIT_CONFIG_GLOBAL="$tmp/gitconfig" GIT_CONFIG_NOSYSTEM=1
printf '[user]\n\tname = test\n\temail = test@example.invalid\n' > "$GIT_CONFIG_GLOBAL"

# A throwaway repo with a github origin, sitting on its default branch.
repo="$tmp/repo"
git init -q -b main "$repo"
git -C "$repo" remote add origin https://github.com/caneff/agent-skills.git

# gh stub: `gh api user` prints $STUB_LOGIN, `gh repo view` prints $STUB_OWNER/name.
# Either being empty makes the stub exit non-zero, standing in for "gh broke".
# With $STUB_REPOS naming a file, `gh repo view <url> ... -q <filter>` answers
# per repo instead: each line is `<owner/name> <owner login> <isFork> <parent
# owner/name or ->`, the filter runs over that repo's JSON, a repo not listed
# is GitHub's "Could not resolve", and an empty $STUB_LOGIN fails every call.
stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/gh" <<'STUB'
#!/usr/bin/env bash
if [ -n "${STUB_REPOS:-}" ] && [ "$1 $2" = "repo view" ]; then
  [ -n "${STUB_LOGIN:-}" ] || { echo "${STUB_ERR:-}" >&2; exit 1; }
  slug=${3#*github.com}; slug=${slug#[:/]}; slug=${slug%/}; slug=${slug%.git}
  filter=.; prev=
  for a in "$@"; do [ "$prev" = -q ] && filter=$a; prev=$a; done
  line=$(awk -v s="$slug" 'tolower($1) == tolower(s)' "$STUB_REPOS")
  [ -n "$line" ] || { echo "GraphQL: Could not resolve to a Repository with the name '$slug'. (repository)" >&2; exit 1; }
  read -r name owner fork parent <<< "$line"
  jq -rn --arg n "${name#*/}" --arg o "$owner" --argjson f "$fork" --arg p "$parent" \
    '{name: $n, owner: {login: $o}, isFork: $f,
      parent: (if $p == "-" then null else {owner: {login: ($p | split("/")[0])}, name: ($p | split("/")[1])} end)}' \
    | jq -r "$filter"
  exit
fi
case "$1 $2" in
  "api user")  [ -n "${STUB_LOGIN:-}" ] || { echo "${STUB_ERR:-}" >&2; exit 1; }; printf '%s\n' "$STUB_LOGIN" ;;
  "repo view") [ -n "${STUB_OWNER:-}" ] || { echo "${STUB_ERR:-}" >&2; exit 1; }; printf '%s/agent-skills\n' "$STUB_OWNER" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stubdir/gh"

fails=0
# run <name> <expected-exit> <command-string> [<substring stderr must contain>]
# RUN_CWD picks the directory (default $repo); RUN_FORBID is a substring stderr must not hold.
run() {
  local name=$1 want=$2 cmd=$3 needle=${4:-}
  local out rc
  out=$(printf '%s' "$cmd" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
        | (cd "${RUN_CWD:-$repo}" && PATH="$stubdir:$PATH" bash "$hook") 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL: $name — stderr missing '$needle'"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "${RUN_FORBID:-}" ] && [[ "$out" == *"$RUN_FORBID"* ]]; then
    echo "FAIL: $name — stderr holds '$RUN_FORBID'"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

# Owned repo (origin owner == gh login): a push of code to the default branch.
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "owned repo: push code to default branch allowed" 0 "git push origin main"
run "owned repo: force-with-lease allowed" 0 "git push --force-with-lease origin main"

# repo_is_owned itself compares origin owner to login case-insensitively
# (#810): `gh repo view` can report the owner in a different case than the
# login (or vice versa) and this checkout is still owned.
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=CANEFF
run "checkout owned when repo-view owner case differs from login" 0 "git push origin main"
export STUB_LOGIN=caneff STUB_OWNER=caneff

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

# A gh failure is named as one, not dressed as a foreign repo (#1293).
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN= STUB_OWNER= STUB_ERR="boom: network unreachable"
RUN_FORBID="you don't own" run "gh failure with no cache names the verify failure, with gh's error" 2 \
  "git push origin main" "could not verify ownership of caneff/agent-skills (gh: boom: network unreachable)"
unset STUB_ERR
export STUB_LOGIN=caneff STUB_OWNER=someone-else
rm -rf "$XDG_CACHE_HOME"
RUN_FORBID="could not verify" run "foreign origin prints the not-owned line, no hedge" 2 "git push origin main" "pushing to a repo you don't own."

# Outside any repo nothing can be verified: stay closed (#1293).
export STUB_LOGIN=caneff STUB_OWNER=caneff
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$tmp" run "outside a git repo: push blocked" 2 "git push origin main" "BLOCKED"

# The verdict is keyed on origin, not worktree path: a second worktree of an
# owned repo is allowed with gh down (#1293).
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER=caneff
run "owned repo: first worktree earns the verdict" 0 "git push origin main"
git -C "$repo" commit -q --allow-empty -m init
git -C "$repo" worktree add -q "$tmp/wt2" -b wt2
export STUB_LOGIN= STUB_OWNER=
RUN_CWD="$tmp/wt2" run "second worktree of an owned repo allowed with gh down" 0 "git push origin wt2"

# Every URL form of the same origin shares one verdict; a look-alike does not.
git -C "$repo" worktree add -q "$tmp/wt3" -b wt3
git -C "$tmp/wt3" remote set-url origin git@github.com:CANEFF/agent-skills.git
RUN_CWD="$tmp/wt3" run "scp-style, mixed-case origin shares the cached verdict" 0 "git push origin wt3"
git -C "$tmp/wt3" remote set-url origin https://github.com/caneff-agent/skills.git
RUN_CWD="$tmp/wt3" run "look-alike repo name does not share the cached verdict" 2 "git push origin wt3" "could not verify"

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
run "pr_settle.py --merge allowed on owned repo" 0 \
  "python3 ~/.agents/skills/implement/pr_settle.py 12 --repo caneff/agent-skills --head abc --merge"
run "pr_settle.py --merge naming someone else's repo blocked" 2 \
  "python3 ~/.agents/skills/implement/pr_settle.py 12 --repo someone-else/agent-skills --head abc --merge" "BLOCKED"
run "pr_settle.py without --merge is a read, allowed on someone else's repo" 0 \
  "python3 ~/.agents/skills/implement/pr_settle.py 12 --repo someone-else/agent-skills"
run "gh pr merge on someone else's PR URL blocked" 2 \
  "gh pr merge https://github.com/someone-else/agent-skills/pull/12 --squash" "BLOCKED"
# A --repo that is a filesystem path names no repo owner (#803). The controller's
# merge in implement/SKILL.md § The merge is followed by merge-cleanup --repo <path>.
run "owned merge chained with merge-cleanup --repo <path> allowed" 0 \
  "gh pr merge 1 --repo caneff/x --squash && merge-cleanup --repo /home/caneff/.agents/skills b"
run "owned merge chained with -R ./repo on another command allowed" 0 \
  "gh pr merge 1 --repo caneff/x && some-tool -R ./repo"
run "owned merge chained with --repo ~/src/x on another command allowed" 0 \
  "gh pr merge 1 --repo caneff/x && some-tool --repo ~/src/x"
run "owned merge chained with a four-segment relative --repo path allowed" 0 \
  "gh pr merge 1 --repo caneff/x && some-tool --repo src/someone-else/x/y"
run "owned merge chained with a two-segment absolute --repo path allowed" 0 \
  "gh pr merge 1 --repo caneff/x && some-tool --repo /srv/x"
run "gh pr merge naming an owned repo in host form allowed" 0 \
  "gh pr merge 1 --repo github.com/caneff/x"
run "gh pr merge naming someone else's repo in host form blocked" 2 \
  "gh pr merge 1 --repo github.com/someone-else/x" "BLOCKED"
# gh takes a URL as --repo too: its OWNER is the segment after the host (a
# user@ stays in the host), and a URL with no OWNER there fails closed.
run "gh pr merge naming an owned repo by https URL allowed" 0 \
  "gh pr merge 1 --repo https://github.com/caneff/agent-skills"
run "gh pr merge naming someone else's repo by https URL blocked" 2 \
  "gh pr merge 1 --repo https://github.com/someone-else/x" "BLOCKED"
run "GH_REPO naming someone else's repo by https URL blocked" 2 \
  "GH_REPO=https://github.com/someone-else/x gh pr merge 1" "BLOCKED"
# The scanner (command-scan-lib.sh) decides what text is a command. Each case
# below is a foreign merge the scanner must still see, or text it must not
# take for one.
run "foreign merge after a comment holding an apostrophe blocked" 2 \
  "# don't skip this
gh pr merge 1 --repo someone-else/x" "BLOCKED"
run "foreign merge after an escaped space before # blocked" 2 \
  'echo a\ #x; gh pr merge 5 --repo someone-else/x' "BLOCKED"
run "foreign merge after a here-string blocked" 2 \
  "cat <<<x
gh pr merge 5 --repo someone-else/x" "BLOCKED"
run "foreign merge after a shift in arithmetic blocked" 2 \
  'echo $((a << b))
gh pr merge 5 --repo someone-else/x' "BLOCKED"
run "foreign merge inside a heredoc body is text" 0 \
  "cat > notes.md <<'EOF'
gh pr merge 5 --repo someone-else/x
EOF"
run "gh pr merge naming someone else's repo by ssh URL blocked" 2 \
  "gh pr merge 1 --repo ssh://git@github.com/someone-else/x" "BLOCKED"
run "gh pr merge with a URL --repo naming no owner blocked" 2 \
  "gh pr merge 1 --repo https://github.com" "BLOCKED"
# scp-style `user@host:OWNER/REPO` (#805): no scheme, so OWNER sits after the
# colon in the first slash-segment, not the whole host:owner chunk.
run "gh pr merge naming an owned repo by scp-style --repo allowed" 0 \
  "gh pr merge 1 --repo git@github.com:caneff/x"
run "gh pr merge naming an owned repo by scp-style -R allowed" 0 \
  "gh pr merge 1 -R git@github.com:caneff/x"
run "GH_REPO naming an owned repo by scp-style value allowed" 0 \
  "GH_REPO=git@github.com:caneff/x gh pr merge 1"
run "gh pr merge naming someone else's repo by scp-style --repo blocked" 2 \
  "gh pr merge 1 --repo git@github.com:someone-else/x" "BLOCKED"
run "GH_REPO naming someone else's repo by scp-style value blocked" 2 \
  "GH_REPO=git@github.com:someone-else/x gh pr merge 1" "BLOCKED"
run "gh pr merge naming someone else's repo by scp-style -R blocked" 2 \
  "gh pr merge 1 -R git@github.com:someone-else/x" "BLOCKED"
run "gh pr merge with a scp-style --repo naming no owner blocked" 2 \
  "gh pr merge 1 --repo git@github.com:x" "BLOCKED"
run "owned merge chained with a one-segment -R value allowed" 0 \
  "gh pr merge 1 --repo caneff/x && grep -R pattern ."
run "someone else's repo on the merge still blocked beside a path --repo" 2 \
  "merge-cleanup --repo /home/caneff/.agents/skills b && gh pr merge 1 --repo someone-else/x" "BLOCKED"
# Same rationale as the repo_is_owned case above (#810), for a named owner.
run "gh pr merge naming an owned repo in a different case allowed" 0 \
  "gh pr merge 1 --repo CANEFF/agent-skills"
run "gh pr merge naming someone else's repo in a different case blocked" 2 \
  "gh pr merge 1 --repo Someone-Else/agent-skills" "BLOCKED"

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
  "gh issue comment 5 --body 'run \`gh pr merge 12\` after CLEAN'"
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
# on gh-pr-merge-specific wording for a different pattern. The rest of the
# message is prose, which this suite does not pin.
run "history destroyer message names its own pattern, not gh pr merge" 2 \
  "git reset --hard HEAD~3" "protected pattern 'git reset --hard'"

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

# The merge block tells a gh failure from a foreign repo, as the push block
# does (#1309).
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN= STUB_OWNER= STUB_ERR="boom: network unreachable"
RUN_FORBID="you don't own" run "merge with gh failing names the verify failure, with gh's error" 2 \
  "gh pr merge 12 --squash" "(gh: boom: network unreachable)"
unset STUB_ERR
export STUB_LOGIN=caneff STUB_OWNER=someone-else
rm -rf "$XDG_CACHE_HOME"
RUN_FORBID="could not verify" run "merge on a foreign origin prints the not-owned line, no hedge" 2 \
  "gh pr merge 12 --squash" "merges a PR on a repo you don't own."

# gh answering that the repo does not exist for this login is an answer,
# not a blip to retry: the repo is not this login's (#1309).
rm -rf "$XDG_CACHE_HOME"
export STUB_LOGIN=caneff STUB_OWNER= \
  STUB_ERR="GraphQL: Could not resolve to a Repository with the name 'caneff/agent-skills'. (repository)"
RUN_FORBID="could not verify" run "repo gh cannot see is not owned, not a lookup failure" 2 \
  "git push origin main" "pushing to a repo you don't own."
run "repo gh cannot see: the block carries gh's answer and the token hint" 2 \
  "git push origin main" "the gh token cannot see it"
unset STUB_ERR
export STUB_LOGIN=caneff STUB_OWNER=caneff

# A merge outside any checkout is unverifiable, not foreign (#1309).
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$tmp" RUN_FORBID="you don't own" run "merge outside a checkout is a lookup failure" 2 \
  "gh pr merge 12 --repo caneff/agent-skills" "could not verify ownership of this checkout (not inside a git checkout)"

# The merge's own login read keeps gh's error text (#1309).
rm -rf "$XDG_CACHE_HOME"
# Prime the ownership cache with an owned verdict on this checkout's PR base;
# no assertion of its own, the cases below read it. A merge earns it: a push
# earns a verdict on the remote it sends to, which never vouches for a base.
printf '%s' "gh pr merge 12 --squash" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
  | (cd "$repo" && PATH="$stubdir:$PATH" bash "$hook") >/dev/null 2>&1
export STUB_LOGIN= STUB_ERR="boom2: login read failed"
RUN_FORBID="you don't own" run "merge naming a repo, login read failing, keeps gh's text" 2 \
  "gh pr merge 1 --repo caneff/x" "(gh: boom2: login read failed)"
RUN_FORBID="ownership of caneff-agent/skills" run "merge naming a repo, login read failing, names that repo's owner" 2 \
  "gh pr merge 1 --repo caneff/x" "could not verify ownership of the repo the command names (owner caneff)"
unset STUB_ERR
export STUB_LOGIN=caneff STUB_OWNER=caneff

# A push is judged by the repo it is sent to, with no fork->parent
# substitution, and a PR by its base repo (Chris, 2026-11-09: caneff/penpa-edit
# is a fork of swaroopg92/penpa-edit that publishes from its own master and
# never PRs upstream). The checkout below is that fork: origin is the owned
# fork, upstream its parent, which someone else owns.
fork="$tmp/fork"
git init -q -b master "$fork"
git -C "$fork" remote add origin https://github.com/caneff/penpa-edit.git
git -C "$fork" remote add upstream https://github.com/swaroopg92/penpa-edit.git
solo="$tmp/solo"
git init -q -b main "$solo"
git -C "$solo" remote add origin git@github.com:caneff/solo.git
cat > "$tmp/repos" <<'EOF'
caneff/penpa-edit caneff true swaroopg92/penpa-edit
swaroopg92/penpa-edit swaroopg92 false -
caneff/solo caneff false -
someone-else/fork someone-else true caneff/solo
EOF
export STUB_REPOS="$tmp/repos" STUB_LOGIN=caneff
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$fork" run "owned fork: push to origin allowed" 0 "git push origin master"
RUN_CWD="$fork" run "owned fork: bare push goes to origin, allowed" 0 "git push"
RUN_CWD="$fork" run "owned fork: push to the named non-owned remote blocked" 2 \
  "git push upstream master" "swaroopg92/penpa-edit"
run "owned fork: -C push to the named non-owned remote blocked" 2 \
  "git -C $fork push -u upstream master" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "owned fork: push to a non-owned URL blocked" 2 \
  "git push https://github.com/swaroopg92/penpa-edit.git master" "BLOCKED"
RUN_CWD="$fork" run "owned fork: a later push in the chain to a non-owned remote blocked" 2 \
  "git push origin master && git push upstream master" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "owned fork: --repo naming the non-owned remote blocked" 2 \
  "git push --repo=upstream" "swaroopg92/penpa-edit"
RUN_FORBID="retry" RUN_CWD="$fork" run "push: a remote read from a shell variable is refused, not called a blip" 2 \
  'git push "$R" master' "cannot tell where to"
# A target the push parser cannot read as a configured remote fails closed:
# the old guard blocked each of these in a foreign checkout.
RUN_CWD="$fork" run "push: a backslash-newline before the remote still reads it" 2 \
  "git push \\
upstream master" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "push: a subshell around the push still reads the remote" 2 \
  "( git push upstream)" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "push: a word that is no remote, URL or path is refused" 2 \
  "git push nosuchremote master" "no remote configured"
RUN_CWD="$fork" run "push: a comment on the push line is refused" 2 \
  "git push origin master # note" "cannot tell where to"
RUN_CWD="$solo" run "push: a cd into another checkout is refused, naming -C" 2 \
  "cd $fork && git push upstream master" "git -C <absolute path> push"
RUN_CWD="$fork" run "push: -o's value is not read as the remote" 2 \
  "git push -o ci.skip upstream master" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "push: -o's value is skipped on an owned remote too" 0 \
  "git push -o ci.skip origin master"
RUN_CWD="$fork" run "push: git -c before the verb still judged" 2 \
  "git -c push.default=current push upstream master" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "push: git --no-pager before the verb still judged" 2 \
  "git --no-pager push upstream master" "swaroopg92/penpa-edit"
RUN_FORBID="SECRET" RUN_CWD="$fork" run "push: a token in a spelled-out URL never reaches the block text" 2 \
  "git push https://tok:SECRET@github.com/swaroopg92/penpa-edit.git master" "swaroopg92/penpa-edit"
git -C "$fork" config branch.master.pushRemote upstream
RUN_CWD="$fork" run "owned fork: bare push to a non-owned pushRemote blocked" 2 \
  "git push" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "owned fork: backgrounded bare push to a non-owned pushRemote blocked" 2 \
  "git push &" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "owned fork: named origin overrides a non-owned pushRemote" 0 "git push origin master"
git -C "$fork" config --unset branch.master.pushRemote
git -C "$fork" config remote.pushDefault upstream
RUN_CWD="$fork" run "owned fork: bare push to a non-owned pushDefault blocked" 2 "git push 2>&1" "swaroopg92/penpa-edit"
git -C "$fork" config --unset remote.pushDefault
git -C "$fork" config branch.master.remote upstream
RUN_CWD="$fork" run "owned fork: bare push to a non-owned branch remote blocked" 2 "git push" "swaroopg92/penpa-edit"
git -C "$fork" config --unset branch.master.remote
git -C "$fork" remote set-url --push origin https://github.com/swaroopg92/penpa-edit.git
RUN_CWD="$fork" run "owned fork: origin whose push URL is non-owned blocked" 2 \
  "git push origin master" "swaroopg92/penpa-edit"
git -C "$fork" remote set-url --delete --push origin https://github.com/swaroopg92/penpa-edit.git

# `gh pr create` is gated on the PR's base: every repo the command names, and
# unless the create names its own, every repo gh could default to (each
# remote, a fork's parent, a set-default repo).
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$fork" run "owned fork: gh pr new, gh's alias, blocked" 2 \
  "gh pr new --title t" "! gh pr create"
RUN_CWD="$fork" run "owned fork: repo flag between pr and create naming the parent blocked" 2 \
  "gh pr --repo swaroopg92/penpa-edit create --title t" "! gh pr create"
RUN_CWD="$fork" run "owned fork: repo flag between pr and create naming the fork allowed" 0 \
  "gh pr -R caneff/penpa-edit create --title t"
RUN_CWD="$fork" run "owned fork: an owned --repo only inside the body text does not set the base" 2 \
  "gh pr create --title t --body 'use --repo caneff/penpa-edit'" "! gh pr create"
RUN_CWD="$fork" run "owned fork: gh pr create in a heredoc fed to sh blocked" 2 \
  $'sh <<EOF\ngh pr create --title t\nEOF' "BLOCKED"
RUN_CWD="$solo" run "owned non-fork: a quoted ; does not hide a foreign --repo" 2 \
  "gh pr create --title \"a; b\" --repo someone-else/x" "! gh pr create"
RUN_CWD="$solo" run "owned non-fork: an exported GH_REPO naming a foreign repo blocked" 2 \
  "export GH_REPO=someone-else/x; gh pr create --title t" "! gh pr create"
RUN_CWD="$solo" run "owned non-fork: a cd before gh pr create is refused" 2 \
  "cd $fork && gh pr create --title t" "cannot tell its base"
git -C "$solo" remote add upstream https://github.com/swaroopg92/penpa-edit.git
RUN_CWD="$solo" run "owned non-fork with a foreign upstream remote: default base blocked" 2 \
  "gh pr create --title t" "swaroopg92/penpa-edit"
git -C "$solo" remote remove upstream
git -C "$solo" config remote.origin.gh-resolved swaroopg92/penpa-edit
RUN_CWD="$solo" run "owned non-fork whose gh set-default is foreign: default base blocked" 2 \
  "gh pr create --title t" "swaroopg92/penpa-edit"
git -C "$solo" config --unset remote.origin.gh-resolved
RUN_CWD="$fork" run "owned fork: gh pr create with the default base (parent) blocked" 2 \
  "gh pr create --title t --body b" "! gh pr create"
RUN_CWD="$fork" run "owned fork: the block names the parent base" 2 \
  "gh pr create --title t --body b" "swaroopg92/penpa-edit"
RUN_CWD="$fork" run "owned fork: gh pr create -R the owned fork allowed" 0 \
  "gh pr create -R caneff/penpa-edit --title t --body b"
RUN_CWD="$fork" run "owned fork: gh pr create --repo the parent blocked" 2 \
  "gh pr create --repo swaroopg92/penpa-edit --title t" "! gh pr create"
RUN_CWD="$fork" run "owned fork: an owned --repo on another command does not set the base" 2 \
  "gh pr view 1 --repo caneff/penpa-edit && gh pr create --title t" "! gh pr create"
RUN_CWD="$fork" run "owned fork: gh pr create handed to bash -c blocked" 2 \
  "bash -c 'gh pr create --title t'" "! gh pr create"
RUN_CWD="$fork" run "gh pr create named in a commit message allowed" 0 \
  "git commit -m \"docs: then run gh pr create\""

# A non-fork owned repo is unchanged: push and PR both allowed.
RUN_CWD="$solo" run "owned non-fork: push allowed" 0 "git push origin main"
RUN_CWD="$solo" run "owned non-fork: gh pr create allowed" 0 "gh pr create --title t --body b"

# The cache keys a verdict on the slug it judged: an owned verdict on the fork
# (from the pushes above) must never clear its parent, as a PR base or a
# merge, when gh is down.
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$fork" run "owned fork: push earns a cached verdict" 0 "git push origin master"
export STUB_LOGIN=
RUN_CWD="$fork" run "owned fork, gh down: cached push verdict still allows the push" 0 "git push origin master"
RUN_CWD="$fork" run "owned fork, gh down: the fork's verdict does not clear a PR to its parent" 2 \
  "gh pr create --title t" "BLOCKED"
RUN_CWD="$fork" run "owned fork, gh down: the fork's verdict does not clear a merge on its parent" 2 \
  "gh pr merge 3 --squash" "BLOCKED"
# An entry written under the old fork->parent rule holds the parent, not its
# own slug: someone else's fork of an owned repo was cached as owned. It must
# be re-asked, not trusted.
mkdir -p "$XDG_CACHE_HOME/claude-git-guard"
printf 'caneff/solo\n' > "$XDG_CACHE_HOME/claude-git-guard/someone-else@fork"
git -C "$fork" remote add theirs https://github.com/someone-else/fork.git
RUN_CWD="$fork" run "old fork->parent cache entry does not clear a push to the fork" 2 \
  "git push theirs master" "BLOCKED"
export STUB_LOGIN=caneff
RUN_CWD="$fork" run "someone else's fork of an owned repo: push blocked" 2 \
  "git push theirs master" "someone-else/fork"
# A merge judges origin's base, a fork's parent, except the standalone fork of
# WORKFLOW.md § Gate 1 (#1716): origin made the gh default, so origin decides.
notmine="merges a PR on a repo you don't own."
rm -rf "$XDG_CACHE_HOME"
RUN_CWD="$fork" run "fork without the gh-default marker: merge judged as the parent's" 2 \
  "gh pr merge 12 --squash" "$notmine"
git -C "$fork" config remote.origin.gh-resolved base
RUN_CWD="$fork" run "standalone fork: merge allowed" 0 "gh pr merge 12 --squash"
RUN_CWD="$fork" run "standalone fork: a merge naming the parent still blocked" 2 \
  "gh pr merge 12 --repo swaroopg92/penpa-edit --squash" "$notmine"
RUN_CWD="$fork" run "standalone fork: a push to the parent still blocked" 2 \
  "git push upstream master" "swaroopg92/penpa-edit"
git -C "$fork" config --unset remote.origin.gh-resolved
RUN_CWD="$fork" run "marker removed: merge judged as the parent's again" 2 \
  "gh pr merge 12 --squash" "$notmine"
git -C "$fork" config remote.upstream.gh-resolved base
RUN_CWD="$fork" run "gh default on another remote is not the marker" 2 \
  "gh pr merge 12 --squash" "$notmine"
git -C "$fork" config --unset remote.upstream.gh-resolved
unset STUB_REPOS
export STUB_LOGIN=caneff STUB_OWNER=caneff

# Declaring a fork standalone is the user's call, so the agent cannot set the
# marker that loosens the merge check; reading it stays allowed.
run "agent setting the gh default blocked" 2 "gh repo set-default caneff/agent-skills" "standalone"
run "agent writing the gh-resolved marker blocked" 2 \
  "git -C /r config remote.origin.gh-resolved base" "standalone"
run "agent unsetting the gh default blocked" 2 "gh repo set-default --unset" "standalone"
run "reading the gh default allowed" 0 "gh repo set-default --view"
run "reading the gh-resolved marker allowed" 0 "git config --get remote.origin.gh-resolved"
run "the marker named in a commit message allowed" 0 \
  "git commit -m 'needs gh repo set-default first'"

# Reading git is untouched.
run "ordinary git command allowed" 0 "git status"

# The dot-pathspec discard (#1387, #1539): blocked everywhere, except a linked
# worktree under .scratch/, a disposable copy where discarding every change is
# the point. The target is `git -C <path>` or the cwd, resolved. The mutation-*
# cases below are the original ones; the wider rule has its own block after.
mkdir -p "$repo/.scratch" "$repo/.claude/worktrees"
git -C "$repo" worktree add -q --detach "$repo/.scratch/mutation-m1"
git -C "$repo" worktree add -q --detach "$repo/.claude/worktrees/implement-9"
mkdir -p "$repo/plain/.scratch/mutation-fake"   # named like one, not a worktree
blocked="discards every uncommitted change under '.'"
run "dot discard: -C a mutation worktree allowed" 0 \
  "git -C $repo/.scratch/mutation-m1 checkout -q -- ."
RUN_CWD="$repo/.scratch/mutation-m1" run "dot discard: cwd in a mutation worktree allowed" 0 \
  "git checkout -- ."
RUN_CWD="$repo/.scratch/mutation-m1" run "dot discard: restore in a mutation worktree allowed" 0 \
  "git restore --worktree ."
run "dot discard: primary checkout blocked" 2 "git checkout -- ." "$blocked"
RUN_CWD="$repo/.claude/worktrees/implement-9" run "dot discard: implement-* worktree blocked" 2 \
  "git checkout -- ." "$blocked"
run "dot discard: -C that backs out of a mutation path blocked" 2 \
  "git -C $repo/.scratch/mutation-m1/../.. checkout -- ." "$blocked"
run "dot discard: -C that backs out of a mutation path into another worktree blocked" 2 \
  "git -C $repo/.scratch/mutation-m1/../../.claude/worktrees/implement-9 checkout -- ." "$blocked"
run "dot discard: git -c key=value before the verb blocked" 2 \
  "git -c core.fsmonitor=false checkout -- ." "$blocked"
run "dot discard: --work-tree before the verb blocked" 2 \
  "git --work-tree=$repo checkout -- ." "$blocked"
run "dot discard: inside a subshell blocked" 2 "(git checkout -- .)" "$blocked"
run "dot discard: quoted -C a mutation worktree allowed" 0 \
  "git -C \"$repo/.scratch/mutation-m1\" checkout -q -- ."
RUN_CWD="$repo/.scratch/mutation-m1" run "dot discard: cd out of the mutation cwd blocked" 2 \
  "cd $repo && git checkout -- ." "$blocked"
RUN_CWD="$repo/.scratch/mutation-m1" run "dot discard: GIT_WORK_TREE naming the primary blocked" 2 \
  "GIT_DIR=$repo/.git GIT_WORK_TREE=$repo git checkout -- ." "$blocked"
run "dot discard: a second -C hidden in a comment blocked" 2 \
  "git -C $repo checkout -- . # git -C $repo/.scratch/mutation-m1" "$blocked"
mkdir -p "$repo/.claude/worktrees/implement-9/.scratch/mutation-fake"
run "dot discard: mutation-named dir inside another worktree blocked" 2 \
  "git -C $repo/.claude/worktrees/implement-9/.scratch/mutation-fake checkout -- ." "$blocked"
run "dot discard: mutation-named dir that is no worktree blocked" 2 \
  "git -C $repo/plain/.scratch/mutation-fake checkout -- ." "$blocked"
run "dot discard: allowed target chained to a blocked one blocked" 2 \
  "git -C $repo/.scratch/mutation-m1 checkout -- . && git checkout -- ." "$blocked"

# The exemption covers any linked worktree under .scratch/, not a named set of
# prefixes (#1539, Chris's ruling 2026-10-11): `.scratch/` is throwaway by
# convention, and a prefix list refuses the next spike name the same way.
git -C "$repo" worktree add -q --detach "$repo/.scratch/spike-s1"
mkdir -p "$repo/.scratch/deep"
git -C "$repo" worktree add -q --detach "$repo/.scratch/deep/spike-s2"
run "dot discard: -C a non-mutation .scratch worktree allowed" 0 \
  "git -C $repo/.scratch/spike-s1 checkout -q -- ."
RUN_CWD="$repo/.scratch/spike-s1" run "dot discard: cwd in a non-mutation .scratch worktree allowed" 0 \
  "git restore --worktree ."
run "dot discard: -C a nested .scratch worktree allowed" 0 \
  "git -C $repo/.scratch/deep/spike-s2 checkout -- ."
mkdir -p "$repo/.scratch/plain-dir"
run "dot discard: .scratch dir that is no worktree blocked" 2 \
  "git -C $repo/.scratch/plain-dir checkout -- ." "$blocked"
run "dot discard: .scratch worktree chained to a primary discard blocked" 2 \
  "git -C $repo/.scratch/spike-s1 checkout -- . && git checkout -- ." "$blocked"

# A standalone repository under .scratch/ is no linked worktree: only the
# linked check keeps a discard there blocked (C3).
git init -q "$repo/.scratch/standalone"
run "dot discard: standalone repo under .scratch blocked" 2 \
  "git -C $repo/.scratch/standalone checkout -- ." "$blocked"
run "dot discard: quoted text naming a discard allowed" 0 \
  "git commit -m \"docs: use git checkout -- . to discard\""
run "dot discard: quoted text then a real discard blocked" 2 \
  "git commit -m \"git checkout -- .\" && git checkout -- ." "$blocked"
run "dot discard: quoted -C path to the primary still blocked" 2 \
  "git -C \"$repo\" checkout -- ." "$blocked"

# The destroyer patterns match the git command run, not text in an argument
# (#1539): quoted text is data, as in the stash and PR-merge guards.
run "destroyer text: single-quoted rg pattern allowed" 0 \
  "rg -n 'reset --hard' docs"
run "destroyer text: double-quoted grep pattern allowed" 0 \
  "grep -rn \"git branch -D\" docs"
run "destroyer text: commit message naming a destroyer allowed" 0 \
  "git commit -m \"docs: explain git clean -fd and reset --hard\""
run "destroyer text: quoted text then a real destroyer blocked" 2 \
  "echo 'reset --hard' && git reset --hard HEAD~1" "protected pattern"
run "destroyer text: unquoted destroyer blocked" 2 "git clean -fd" "protected pattern 'git clean -fd'"
run "destroyer text: destroyer handed to sh -c blocked" 2 \
  "sh -c 'git reset --hard HEAD'" "protected pattern"
run "destroyer text: destroyer handed to eval blocked" 2 \
  "eval \"git branch -D x\"" "protected pattern"
run "destroyer text: destroyer in a command substitution blocked" 2 \
  "echo \"\$(git reset --hard)\"" "protected pattern"
run "destroyer text: destroyer piped into a shell blocked" 2 \
  "echo 'git branch -D x' | bash" "protected pattern"
# Commands that hand their quoted argument to a shell (C1), shells named by
# path or with flags before -c (C2), a heredoc into a shell (P1).
run "destroyer text: submodule foreach blocked" 2 \
  "git submodule foreach --recursive 'git clean -fd'" "protected pattern"
run "destroyer text: rebase -x blocked" 2 \
  "git rebase -x 'git reset --hard HEAD' main" "protected pattern"
run "destroyer text: git alias with a shell body blocked" 2 \
  "git -c alias.nuke='!git reset --hard' nuke" "protected pattern"
run "destroyer text: /bin/sh -c blocked" 2 "/bin/sh -c 'git reset --hard'" "protected pattern"
run "destroyer text: bash -e -c blocked" 2 "bash -e -c 'git reset --hard'" "protected pattern"
run "destroyer text: bash --login -c blocked" 2 "bash --login -c 'git branch -D x'" "protected pattern"
run "destroyer text: dash -c blocked" 2 "dash -c 'git reset --hard'" "protected pattern"
run "destroyer text: pipe into /bin/bash blocked" 2 "echo 'git branch -D x' | /bin/bash" "protected pattern"
run "destroyer text: xargs sh -c blocked" 2 "echo x | xargs sh -c 'git reset --hard'" "protected pattern"
run "destroyer text: heredoc into bash blocked" 2 \
  "bash <<EOF
git reset --hard
EOF" "protected pattern"
run "destroyer text: heredoc into cat naming a destroyer allowed" 0 \
  "cat > notes.md <<EOF
never run git reset --hard here
EOF"
# A command substitution elsewhere in the line does not make the rest code (P2).
run "destroyer text: pattern beside a substitution allowed" 0 \
  "rg \"reset --hard\" \$(git ls-files docs)"
run "destroyer text: message with a substitution allowed" 0 \
  "git commit -m \"fix \$(date): reset --hard text\""
run "destroyer text: multi-line substitution body blocked" 2 \
  "echo \"\$(
git reset --hard
)\"" "protected pattern"

# `git stash` in a linked worker worktree (#1529): the stash stack is shared
# with the primary checkout and every other worktree, so a worker's push or pop
# lands on, or takes, another session's entry. The primary checkout keeps its
# stash; read-only verbs and the apply/drop pair stay allowed everywhere.
wt="$repo/.claude/worktrees/implement-9"
for cmd in "git stash" "git stash push" "git stash push -u -m tag" "git stash save wip" \
           "git stash pop" "git stash -u" "git stash --include-untracked" \
           "git -C $wt stash" "git -c core.x=y stash pop" "git add -A && git stash"; do
  RUN_CWD="$wt" run "stash: '$cmd' in a worker worktree blocked" 2 "$cmd" "git stash"
done
run "stash: -C a worker worktree from the primary blocked" 2 "git -C $wt stash push" "BLOCKED"
RUN_CWD="$wt" run "stash: the message hands off, naming a WIP commit" 2 "git stash" "WIP commit"
RUN_CWD="$wt" run "stash: cd out of the worker cwd blocked, unresolved" 2 "cd /tmp && git stash" "BLOCKED"
RUN_CWD="$wt" run "stash: -C the primary from a worker cwd allowed" 0 "git -C $repo stash"
for cmd in "git stash list" "git stash show -p" "git stash apply stash@{0}" "git stash drop stash@{0}"; do
  RUN_CWD="$wt" run "stash: '$cmd' in a worker worktree allowed" 0 "$cmd"
done
RUN_CWD="$wt" run "stash: words in a commit message allowed" 0 'git commit -m "no git stash pop here"'
RUN_CWD="$wt" run "stash: grep for the verb allowed" 0 "grep -n 'git stash' flow/x.sh"
# Each stash segment is judged by its own target, not the first stash segment's
# (P1/C1): a read-only first segment aimed at the primary must not vouch for
# a later push aimed at a worktree.
RUN_CWD="$wt" run "stash: chain, primary list then cwd pop blocked" 2 \
  "git -C $repo stash list && git stash pop" "linked worktree"
RUN_CWD="$wt" run "stash: chain on separate lines blocked" 2 \
  "git -C $repo stash list
git stash push" "linked worktree"
run "stash: chain, primary list then -C worktree push blocked" 2 \
  "git -C $repo stash list ; git -C $wt stash push" "linked worktree"
run "stash: chain of primary-only stash segments allowed" 0 \
  "git -C $repo stash list && git -C $repo stash push -u"
# A target the hook cannot resolve is refused, from the primary too (C2, S1),
# and the message names that cause, not a linked worktree.
unres="cannot tell which checkout"
RUN_FORBID="from a linked worktree" run "stash: unresolved -C path blocked, cause named" 2 \
  "git -C $repo/.claude/worktrees/nope stash pop" "$unres"
run "stash: -C a shell variable blocked, cause named" 2 \
  'W=x; git -C "$W" stash pop' "$unres"
RUN_FORBID="from a linked worktree" run "stash: cd from the primary blocked, cause named" 2 \
  "cd $repo && git stash" "a cd or pushd"
RUN_FORBID="from a linked worktree" run "stash: GIT_DIR from the primary blocked, cause named" 2 \
  "GIT_DIR=$repo/.git git stash push" "GIT_DIR-style"
RUN_FORBID="from a linked worktree" run "stash: comment from the primary blocked, cause named" 2 \
  "git stash push # note" "a '#'"
RUN_FORBID="from a linked worktree" run "stash: second -C from the primary blocked, cause named" 2 \
  "git -C $repo -C $wt stash push" "more than one -C"
# The stack-changing verbs outside the four the ticket names (C4).
for cmd in "git stash clear" "git stash branch b" "git stash store abc"; do
  RUN_CWD="$wt" run "stash: '$cmd' in a worker worktree blocked" 2 "$cmd" "linked worktree"
done
RUN_CWD="$wt" run "stash: the hand-off names untracked files" 2 "git stash -u" "untracked"
run "stash: push in the primary checkout allowed" 0 "git stash push -u -m tag"
RUN_CWD="$repo/.scratch/mutation-m1" run "stash: push in a mutation worktree blocked" 2 "git stash push" "BLOCKED"

# A command's length must not decide the guard's cost. A quadratic lexer took
# 2.6 s on 44 KB and 5.9 s on 66 KB (#1423), and the teaching hooks, which share
# it, time out at 5 s. 100 KB of quoted words, comments and escapes, no
# heredoc, one line that names `push` and `checkout` so both segment loops run,
# then a foreign merge, must be blocked on CPU time (user+sys, which a busy box
# running suites in parallel does not inflate) well under that.
big=$(awk 'BEGIN { for (i = 0; i < 2500; i++) printf "echo \"a b $i\" '"'"'c d'"'"' x\\ y # note %d\n", i }')
big+=$'\ngit commit -m "do not push yet; checkout notes"\ngh pr merge 5 --repo someone-else/x'
TIMEFORMAT='%U %S'
cpu=$( { time run "foreign merge after a 100 KB command blocked" 2 "$big" "BLOCKED" >/dev/null; } 2>&1 )
if awk -v t="$cpu" 'BEGIN { split(t, p, " "); exit !(p[1] + p[2] < 2.5) }'; then
  echo "PASS: 100 KB command scanned in ${cpu% *}+${cpu#* }s CPU"
else
  echo "FAIL: 100 KB command took '$cpu' s CPU (user sys), want under 2.5s"; fails=1
fi
unset TIMEFORMAT
# A backslash-newline inside double quotes is removed by the shell, so these
# run `gh pr merge` and `bash -c`; the scan must still see one command (#1423).
run "foreign merge: bash -c after a quoted backslash-newline blocked" 2 \
  "bash \"\\
\"-c 'gh pr merge 5 --repo someone-else/x'" "BLOCKED"
run "foreign merge: pipe into bash after a quoted backslash-newline blocked" 2 \
  "echo 'gh pr merge 5 --repo someone-else/x' | \"\\
\"bash" "BLOCKED"
# A lexer that cannot run must not read as a command with nothing in it.
mkdir -p "$tmp/noawk"
# Only the lexer's calls (`-v view=...`) fail; the owner scan's awk still runs.
cat > "$tmp/noawk/awk" <<'STUB'
#!/usr/bin/env bash
[ "$1" = "-v" ] && [[ "$2" == view=* ]] && exit 1
exec /usr/bin/awk "$@"
STUB
chmod +x "$tmp/noawk/awk"
stubdir_saved=$stubdir; stubdir="$tmp/noawk:$stubdir"
run "foreign merge blocked when the lexer's awk fails" 2 \
  "bash -c 'gh pr merge 5 --repo someone-else/x'" "BLOCKED"
stubdir=$stubdir_saved
# A command that names no destroyer, merge, checkout or stash runs no lexer
# pass: the quote views cost two awk forks and are read only once a raw gate
# matches (#1566). The stub logs each lexer call and leaves its answer alone.
mkdir -p "$tmp/countawk"
cat > "$tmp/countawk/awk" <<'STUB'
#!/usr/bin/env bash
[ "$1" = "-v" ] && [[ "$2" == view=* ]] && echo lexed >> "$LEXER_LOG"
exec /usr/bin/awk "$@"
STUB
chmod +x "$tmp/countawk/awk"
export LEXER_LOG="$tmp/lexer.log"
# lexer_passes <command> <want-exit> <want-passes: none|some>
lexer_passes() {
  local cmd=$1 want=$2 passes=$3 out rc
  : > "$LEXER_LOG"
  out=$(printf '%s' "$cmd" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
    | (cd "$repo" && PATH="$tmp/countawk:$stubdir:$PATH" bash "$hook") 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: lexer count '$cmd' — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ "$passes" = none ] && [ -s "$LEXER_LOG" ]; then
    echo "FAIL: '$cmd' ran the lexer ($(wc -l < "$LEXER_LOG") passes)"; fails=1
  elif [ "$passes" = some ] && [ ! -s "$LEXER_LOG" ]; then
    echo "FAIL: '$cmd' never ran the lexer, so the stub counts nothing"; fails=1
  else
    echo "PASS: '$cmd' lexer passes: $passes"
  fi
}
for plain in "git status" "ls -la" "git log --oneline -5"; do
  lexer_passes "$plain" 0 none
done
# The positive control: a command that reaches a raw gate does lex.
lexer_passes "git branch -D x" 2 some
# A whole-tree discard handed to a shell is read as code (#1539): the views
# must be computed for it, not only for a destroyer pattern.
run "discard handed to sh -c blocked" 2 "bash -c \" git checkout -- . \"" "BLOCKED"
run "discard handed to eval blocked" 2 "eval \" git restore . \"" "BLOCKED"
# An inherited memo flag must not switch the lexer off.
out=$(printf '%s' "git branch -D x" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
      | (cd "$repo" && CMD_VIEWS_DONE=1 PATH="$stubdir:$PATH" bash "$hook") 2>&1)
rc=$?
if [ "$rc" = 2 ]; then echo "PASS: an inherited CMD_VIEWS_DONE does not skip the lexer"
else echo "FAIL: inherited CMD_VIEWS_DONE — want exit 2, got $rc: $out"; fails=1; fi
# The guard reads commands through command-scan-lib.sh beside its real path.
# Without the lib no pattern can match, so it blocks every command rather than
# letting each one through unscanned.
mkdir -p "$tmp/nolib"
cp "$hook" "$tmp/nolib/block-dangerous-git.sh"
out=$(printf '%s' "git status" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
      | (cd "$repo" && PATH="$stubdir:$PATH" bash "$tmp/nolib/block-dangerous-git.sh") 2>&1)
rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"command-scan-lib.sh is missing"* ]]; then
  echo "PASS: missing scan lib blocks"
else
  echo "FAIL: missing scan lib — want exit 2 naming the lib, got $rc: $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
