#!/bin/bash
# Git guardrails (PreToolUse, Bash).
#
# Narrow guards; everything else about a push is the agent's business.
#   - PUSH is gated on OWNERSHIP, not on branch or file type, judged by the
#     repo the push is sent to (`push_target` resolves the remote in git's own
#     order). When that repo's owner is the `gh` login, the push is allowed —
#     any branch, any content, default branch included — and a fork counts as
#     itself, never as its parent (Chris, 2026-11-09: a fork he publishes from
#     is his). A repo someone else owns is blocked, and the agent hands the
#     user the push and PR lines to run themselves: the outward-facing step is
#     the user's. A push whose target cannot be told (a `cd`, a comment, a
#     word that is no remote) is refused. The ownership lookup FAILS CLOSED:
#     gh erroring or the network being down means "not owned" means blocked.
#   - `gh pr create` is gated on the PR's base repo (`pr_create_is_owned`):
#     every repo the command names, and every repo gh could default to when
#     the create names none itself. It is what keeps an agent from opening a
#     PR upstream from an owned fork.
#   - `gh pr merge` (and `implement/pr_settle.py ... --merge`, which runs one,
#     #1526) is gated on the same OWNERSHIP (#790): allowed when this
#     checkout's base (a fork's parent, except the standalone fork of
#     WORKFLOW.md § Gate 1, #1716) and every repo the line names are the `gh`
#     login's, blocked everywhere else. Only the command is matched, not the phrase: quoted
#     text (a grep pattern, a commit message) is data unless a shell runs
#     it. The `ready-for-human` exception —
#     the user merges that ticket's PR — is enforced by `/implement`'s prose,
#     not here: a squash merge on the user's own repo is undone with a revert,
#     so a prose miss there costs a revert, not a merge nobody can take back.
#   - Setting the gh default (`gh repo set-default`, or a `git config` write
#     of `gh-resolved`) is refused: it is what declares a fork standalone and
#     loosens the merge check, so it is the user's call (#1716).
#   - `git stash` that adds or takes an entry is refused in a linked worktree
#     (#1529): the stack is shared by every worktree and session.
#   - History/worktree destroyers and bare force-pushes stay blocked; those
#     guard against losing work, not against skipping a review lane.
# The user lands anything via the `!` prefix, which runs in the user's own
# shell and never passes through this hook.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# The lib resolves beside this file's real location: install.sh links this
# hook into ~/.claude/hooks, and the lib is not linked there. Without it no
# pattern below can match, so a missing lib blocks rather than allowing
# every command unscanned.
lib="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/command-scan-lib.sh"
# shellcheck source=command-scan-lib.sh
. "$lib" 2>/dev/null || { echo "BLOCKED: $lib is missing, so this guard cannot scan the command." >&2; exit 2; }

# Detection uses $SCAN (heredoc bodies stripped, see the lib); error messages
# still quote the original $COMMAND.
SCAN=$(printf '%s\n' "$COMMAND" | strip_heredocs)

# What counts as text handed to a shell, defined once for every guard below
# (#1539): quoted text is data unless something runs it. A shell with any flags
# before `-c`, path-qualified or not, `eval`, a pipe or heredoc into a shell,
# and the commands that hand their argument to one (`xargs`, `watch`,
# `parallel`, `ssh`, `tmux send-keys`, `python -c`), plus git's own runners
# (`submodule foreach`, `rebase -x`, a `-c alias.<n>=!...`). Matched in the
# quote-dropped view, so the word `sh` inside a string is not one. A hit makes
# the guard read the raw text, which over-blocks and never lets one through;
# a program that runs its argument under another name is not read, as this
# guard stops a drifting agent, not a determined one.
cmd_start='(^|[;&|(`[:space:]])'
shell_word='([^[:space:];&|(]*/)?(bash|sh|zsh|dash|ksh)'
shell_runners='eval|xargs|watch|parallel|ssh|tmux[[:space:]]+send-keys|python3?[[:space:]]+-c|git[[:space:]]+submodule[[:space:]]+foreach|git[[:space:]]+([^;&|]*[[:space:]])?rebase[[:space:]]([^;&|]*[[:space:]])?(-x|--exec)'
shell_handed="$cmd_start(${shell_word}[[:space:]]+(-[^[:space:]]+[[:space:]]+)*-[a-z]*c|${shell_runners})([[:space:]]|\$)|\|[[:space:]]*${shell_word}([[:space:]]|\$)|${shell_word}[[:space:]]*<<|alias\.[^[:space:]=]+="
# The words a shell runs, from one lexer pass over the whole command: CMD_BARE
# drops quoted text, CMD_EXPANDS keeps what `$(...)` and backticks still run.
# The pass costs two awk forks, so it runs on first need (#1566): a command
# that no raw gate below matches never pays for it.
CMD_VIEWS_DONE=   # owned here: an inherited value would skip the lexer
command_views() {
  [ -n "$CMD_VIEWS_DONE" ] && return 0
  CMD_VIEWS_DONE=1
  quote_views "$SCAN"
  CMD_BARE=$BARE
  CMD_EXPANDS=$EXPANDS
  cmd_handed=0
  printf '%s\n' "$CMD_BARE" | grep -qE "$shell_handed" && cmd_handed=1
  cmd_substitutions=$(printf '%s' "$CMD_EXPANDS" | tr '\n' ' ' | grep -oE '\$\(.*\)|`[^`]*`')
  return 0
}
# The text $1 as command segments, one per line: a backslash-newline is joined
# first, as the shell joins it, then the text is cut at `&&`, `||`, `;` and
# `|`. The cut ignores quotes, so a quoted `;` splits too; a reader that needs
# quotes respected cuts a quote-dropped view instead.
split_segments() {
  printf '%s\n' "$1" | sed -e ':a' -e '/\\$/{N;s/\\\n/ /;ba' -e '}' | sed -E 's/(&&|\|\||;|\|)/\n/g'
}
# A `cd` or `pushd` anywhere in the command: git, and gh, then run somewhere
# this hook cannot read.
cd_re='(^|[;&|(`[:space:]])(cd|pushd)([[:space:]]|$)'
# A `git push`, global options before the verb included (`-C <dir>`,
# `-c <key=value>`, `--no-pager`).
push_re='(^|[;&|(`[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+push([[:space:]]|$)'

# --- Always-blocked: history/worktree destroyers. ---
DANGEROUS_PATTERNS=(
  "git ctm"
  "git-ctm"
  "git reset --hard"
  "reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
)
# `git checkout .` / `git restore .` throw away every uncommitted change in the
# tree. Match on the whole command, not on the two words being adjacent:
# `git restore --worktree .` and `git checkout -- .` are the same destruction
# with a flag in between, and an adjacency pattern misses both.
#
# The one safe form is `git restore --staged` without `--worktree`: that only
# unstages, and leaves the working tree alone.
# `has_dot_pathspec`, `restore_is_unstage_only` and `git_verb` read one command
# segment, so a chain is blocked when any one of its discards is. `git_verb`
# takes the verb first, then the segment.
has_dot_pathspec() { echo "$1" | grep -qE '(^|[[:space:]])\.([[:space:])]|$)'; }
restore_is_unstage_only() {
  echo "$1" | grep -q -- '--staged' && ! echo "$1" | grep -q -- '--worktree'
}
git_verb() {
  echo "$2" | grep -qE "(^|[[:space:](])git([[:space:]]+(-[Cc][[:space:]]+[^[:space:]]+|--[a-z-]+(=[^[:space:]]+)?))*[[:space:]]+$1([[:space:]]|\$)"
}
# The checkout a command segment's git runs in. Anything that can move git
# off the directory this reads is refused rather than parsed (#1387, #1529): a
# `cd`, a `GIT_DIR`-style variable or flag, a second `-C`, a comment, a path
# that does not resolve. The target is `git -C <path>` or the cwd, resolved
# with realpath so a `..` or a symlink cannot name another checkout.
# $1 the segment; $SCAN the whole command. Returns 1, TARGET_WHY saying why,
# when the directory cannot be told; else 0 with TARGET_TOP the checkout's top
# level and TARGET_LINKED 1 when it is a linked worktree (git-dir differs from
# the common dir).
git_target() {
  local dir real gitdir common
  TARGET_TOP="" TARGET_LINKED=0
  TARGET_WHY="a cd or pushd in the command"
  echo "$SCAN" | grep -qE "$cd_re" && return 1
  TARGET_WHY="a GIT_DIR-style variable or flag"
  echo "$SCAN" | grep -qE 'GIT_(DIR|WORK_TREE|COMMON_DIR)=|--(git-dir|work-tree)' && return 1
  TARGET_WHY="a '#' in the command"
  case "$1" in *'#'*) return 1 ;; esac
  TARGET_WHY="more than one -C"
  [ "$(echo "$1" | grep -oE '(^|[[:space:]])-C[[:space:]]' | wc -l)" -le 1 ] || return 1
  dir=$(echo "$1" | grep -oE '(^|[[:space:]])-C[[:space:]]+[^[:space:]]+' | sed -E 's/^[[:space:]]*-C[[:space:]]+//')
  dir=$(printf '%s' "${dir:-.}" | tr -d "'\"")
  TARGET_WHY="a -C path that does not resolve to a checkout ('$dir')"
  real=$(realpath -- "$dir" 2>/dev/null) || return 1
  TARGET_TOP=$(git -C "$real" rev-parse --show-toplevel 2>/dev/null) || return 1
  gitdir=$(git -C "$real" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  common=$(git -C "$real" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 1
  [ "$gitdir" != "$common" ] && TARGET_LINKED=1
  return 0
}
# A discard aimed at a linked worktree under `.scratch/` is the point of that
# worktree (#1387, widened from `mutation-*` by #1539): `.scratch/` is
# throwaway by convention, a disposable copy a reviewer or worker plants a
# mutation or a spike in, and a prefix list refuses the next new name. Its top
# level must itself sit under `.scratch/` and be a linked one: a plain
# directory under `.scratch/`, or one inside another worktree, is not one.
is_scratch_worktree() {
  git_target "$1" || return 1
  case "$TARGET_TOP" in */.scratch/*) ;; *) return 1 ;; esac
  [ "$TARGET_LINKED" = 1 ]
}
discards_worktree() {
  has_dot_pathspec "$1" || return 1
  git_verb checkout "$1" || { git_verb restore "$1" && ! restore_is_unstage_only "$1"; } || return 1
  # `git commit -m "... git checkout -- . ..."` names a discard without
  # running one (#1539): the verb and the dot must both be words the shell
  # runs, unless a shell is handed the text. The unquoted words are only a
  # gate, so a quoted `-C` path cannot hide the target from the check above.
  command_views
  if [ "$cmd_handed" != 1 ]; then
    quote_views "$1"
    has_dot_pathspec "$BARE" && echo "$BARE" | grep -qwE 'checkout|restore' || return 1
  fi
  ! is_scratch_worktree "$1"
}
# The two segment loops fork several greps per segment, so each is fed only the
# segments that hold the verb it looks for: a long command of other words costs
# one grep, not a fork per line (#1423).
while IFS= read -r segment; do
  if discards_worktree "$segment"; then
    echo "BLOCKED: '$COMMAND' discards every uncommitted change under '.'. That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
done < <(split_segments "$SCAN" | grep -e checkout -e restore)

# A destroyer is matched in the command run, not in text an argument carries
# (#1539): `rg -n 'reset --hard' docs` and a commit message naming one are
# data. A pattern must be in the raw command (heredoc bodies included) before
# anything else is read, which keeps the lexer's views off the common path.
# It then blocks when it is a word the shell runs (CMD_BARE), when a shell is
# handed the text (`cmd_handed`, above: the raw text is read, heredoc body
# included), or when it sits inside a `$(...)` or backtick body, the only
# quoted text that still runs. A `$(...)` elsewhere in the command does not
# make the rest of it code.
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  printf '%s\n' "$COMMAND" | grep -qE "$pattern" || continue
  command_views
  if printf '%s\n' "$CMD_BARE" | grep -qE "$pattern" || [ "$cmd_handed" = 1 ] \
     || printf '%s\n' "$cmd_substitutions" | grep -qE "$pattern"; then
    hint=""
    [ "$pattern" = "git branch -D" ] && hint=" FIRST try 'git branch -d' (lowercase), which is allowed: git itself refuses it on an unmerged branch, so it deletes the safe ones and needs no hand-off. Hand off only what -d refuses."
    echo "BLOCKED: '$COMMAND' matches protected pattern '$pattern'. That part is the user's, not yours.${hint} HAND OFF: re-run the command without it, then give the user the exact '! $pattern ...' line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
done

# --- Setting the gh default (#1716). ---
# The gh default on origin is what makes a fork standalone (WORKFLOW.md
# § Gate 1), so an agent setting it would loosen the merge check on its own
# say-so; gh's "run gh repo set-default" error invites exactly that. Judged per
# segment, so a read (`--view`, `git config --get`) exempts only itself. The
# key is read with quotes dropped, since `git config "remote.x.gh-resolved"`
# is the same key, while the verb must be a word the shell runs, so a commit
# message naming one is data. A shell handed the text, or a `$(...)` body, is
# read whole and blocks.
sets_gh_default='gh[[:space:]]+repo[[:space:]]+set-default|git[[:space:]]([^;&|]*[[:space:]])?config[[:space:]][^;&|]*gh-resolved'
reads_gh_default='set-default[[:space:]]+(-v|--view)([[:space:]]|$)|config[[:space:]]+(--get|--get-regexp)[[:space:]][^;&|]*gh-resolved'
gh_default_verb='(^|[[:space:](])(gh[[:space:]]+repo|git[[:space:]]([^;&|]*[[:space:]])?config)([[:space:]]|$)'
writes_gh_default() { # <segment>
  local plain
  plain=$(printf '%s' "$1" | tr -d "'\"")
  printf '%s\n' "$plain" | grep -qE "$sets_gh_default" || return 1
  printf '%s\n' "$plain" | grep -qE "$reads_gh_default" && return 1
  quote_views "$1"
  printf '%s\n' "$BARE" | grep -qE "$gh_default_verb"
}
if printf '%s\n' "$COMMAND" | grep -qE "$sets_gh_default"; then
  command_views
  gh_default_set=0
  { [ "$cmd_handed" = 1 ] || printf '%s\n' "$cmd_substitutions" | grep -qE "$sets_gh_default"; } && gh_default_set=1
  while IFS= read -r segment; do
    writes_gh_default "$segment" && gh_default_set=1
  done < <(split_segments "$SCAN" | grep -e set-default -e gh-resolved)
  if [ "$gh_default_set" = 1 ]; then
    echo "BLOCKED: '$COMMAND' sets the gh default repo, which is what declares a fork standalone and loosens the merge check (WORKFLOW.md § Gate 1). That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! gh repo set-default <owner/name>' line to run themselves." >&2
    exit 2
  fi
fi

# --- `git stash` in a linked worktree (#1529). ---
# The stash stack lives in the common git dir: a push from a worker's worktree
# lands on the stack every worktree and session shares, and a pop takes
# whichever entry is on top, which may be another session's. Refused there:
# set work aside with a WIP commit. Allowed are the verbs that only read the
# stack or remove a named entry (`list`, `show`, `apply`, `drop`, `create`),
# so an entry found there can be read and removed; every other form is refused,
# bare `git stash` and one led by an option (an implicit push) included. The
# primary checkout keeps its stash. Each segment is read for its own target,
# with its quoted text dropped, so a verb inside quotes is data; a verb
# handed to a shell (`sh -c`) is not read, as this guard stops a drifting
# agent, not a determined one. A target that cannot be told is refused, since
# the guard cannot say the stack is safe.
stash_opt='(-[^[:space:]]+[[:space:]]+([^-[:space:]][^[:space:]]*[[:space:]]+)?)*'
stash_ok='(list|show|apply|drop|create)'
stash_mutates() { # <segment, quoted text dropped>
  echo "$1" | grep -qE "(^|[[:space:](])git[[:space:]]+${stash_opt}stash([[:space:]]|\$|\))" \
    && ! echo "$1" | grep -qE "(^|[[:space:](])git[[:space:]]+${stash_opt}stash[[:space:]]+${stash_ok}([[:space:]]|\$|\))"
}
stash_handoff() {
  echo "BLOCKED: '$COMMAND' $1. The stash stack is shared by every worktree and session, so a worker never changes it. Set the work aside with a WIP commit instead ('git add -A && git commit -m wip' takes untracked files too) and stack the fix commits on it. 'git stash list', 'show', 'apply' and 'drop' are allowed." >&2
  exit 2
}
if printf '%s\n' "$COMMAND" | grep -q stash; then
  while IFS= read -r segment; do
    quote_views "$segment"
    stash_mutates "$BARE" || continue
    if ! git_target "$segment"; then
      stash_handoff "changes the stash stack, and this guard cannot tell which checkout git runs in (${TARGET_WHY}). Give 'git -C <absolute path> stash ...' with none of those"
    elif [ "$TARGET_LINKED" = 1 ]; then
      stash_handoff "changes the stash stack from a linked worktree"
    fi
  done < <(split_segments "$SCAN" | grep stash)
fi

# --- Bare force-push: blocked. `--force-with-lease` is fine (the lease refuses
# to clobber commits this clone hasn't seen), and still goes through the
# ownership gate below like any other push. Judged per command segment: a
# `--force` that belongs to another command in the chain (`worktree rm
# --force`) or a `push` that is only a word in a path (`hooks/pre-push`) is
# not a force-push (#637). ---
is_force_push_segment() {
  echo "$1" | grep -qE "$push_re" \
    && echo "$1" | grep -qE '[[:space:]](--force([[:space:]]|$)|-f([[:space:]]|$))' \
    && ! echo "$1" | grep -q 'force-with-lease'
}
while IFS= read -r segment; do
  if is_force_push_segment "$segment"; then
    echo "BLOCKED: bare force-push in '$COMMAND' can destroy commits on origin. Use '--force-with-lease', or hand the user the exact '! git push --force ...' line." >&2
    exit 2
  fi
done < <(split_segments "$SCAN" | grep -e push)

# GitHub owners are case-insensitive: `CANEFF/x` and `caneff/x` name the same
# account, so every owner-vs-login compare lowercases both sides first. `tr`
# over bash's `${,,}`: GitHub logins are ASCII, and `${,,}` folds by locale
# (a Turkish locale maps `I` to dotless `ı`, not `i`), which could turn a
# same-account match into a false block.
ieq() { [ "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" = "$(printf '%s' "$2" | tr 'A-Z' 'a-z')" ]; }

# --- Ownership, cached. ---
# A verdict is keyed on the slug it judged (owner/name, read from the URL), so
# one earned once covers every worktree and URL form of that repo, and a fresh
# `implement-*` worktree never re-asks gh. Only the OWNED verdict is cached:
# it's the hot path (allow), so caching it keeps `gh` off every subsequent
# Bash call, while a not-owned/lookup-failed verdict is never written — a
# block is rare, so re-asking costs nothing and a stale "no" (or a cached
# network blip) can never harden into a permanent block. Delete $cache_dir if
# a repo changes hands.
# A verdict entry is trusted only when it holds its own slug. One written
# before 2026-11-09, under the rule that judged a fork by its parent, holds
# the parent: trusting it would let an owned parent clear a push to someone
# else's fork, so it is re-asked instead. A PR-base verdict lives apart, under
# base/, so a fork's own verdict never clears its parent as a base.
# The owned-or-not functions return 0 owned, 1 not owned (gh answered, a repo
# this login cannot see included), 2 ownership could not be read (gh failed,
# or no checkout); on 2, OWNERSHIP_ERR says why, gh's own error text included,
# so the block can say it was a blip. On a repo gh cannot see, OWNERSHIP_ERR
# holds gh's answer. OWNERSHIP_REPO names the repo judged last, for the block.
OWNERSHIP_ERR=""
OWNERSHIP_REPO=""
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-git-guard"
# `/` becomes `@`, which GitHub names cannot hold, so `a-b/c` and `a/b-c`
# never share a key.
cache_key() { printf '%s' "$1" | tr 'A-Z' 'a-z' | tr '/' '@' | tr -c 'a-z0-9@._-' '_'; }
cached_owned() { # <slug>
  local f
  f="$cache_dir/$(cache_key "$1")"
  [ -f "$f" ] && ieq "$(head -n1 "$f")" "$1"
}
cache_owned() { # <slug>
  mkdir -p "$cache_dir" 2>/dev/null && printf '%s\n' "$1" > "$cache_dir/$(cache_key "$1")" 2>/dev/null
}
# https://github.com/o/n.git, git@github.com:o/n.git and ssh://git@github.com/o/n
# all name the same repo, o/n, printed; 1 for a URL off github. The block text
# names the slug, never the URL: a URL can carry a token.
github_slug() {
  local s
  case "$1" in *github.com*) ;; *) return 1 ;; esac
  s=${1#*github.com}; s=${s#[:/]}; s=${s%/}; s=${s%.git}
  printf '%s' "$s"
}
# gh's own error text from the file $1 into OWNERSHIP_ERR; the file is removed.
gh_failed() {
  local text
  text=$([ -n "$1" ] && tr '\n' ' ' < "$1" | sed 's/ *$//')
  OWNERSHIP_ERR="gh: ${text:-no error text}"
  [ -z "$1" ] || rm -f "$1"
}
# The gh login into GH_LOGIN; 2, with OWNERSHIP_ERR set, when gh cannot say.
gh_login() {
  local errf
  errf=$(mktemp 2>/dev/null) || errf=""
  GH_LOGIN=$(gh api user -q .login 2>"${errf:-/dev/null}") || { gh_failed "$errf"; return 2; }
  [ -z "$errf" ] || rm -f "$errf"
  [ -n "$GH_LOGIN" ] || { OWNERSHIP_ERR="gh: empty answer"; return 2; }
}
# The repo at URL $1, read through the jq filter $2, into GH_ANSWER. 1 when gh
# reached GitHub and was told the repo does not exist for this login, 2 when
# gh could not answer. gh's error text goes to a temp file; with none the
# block says so.
gh_repo() {
  local errf
  errf=$(mktemp 2>/dev/null) || errf=""
  GH_ANSWER=$(gh repo view "$1" --json owner,name,isFork,parent -q "$2" 2>"${errf:-/dev/null}") || {
    gh_failed "$errf"
    case "$OWNERSHIP_ERR" in *"Could not resolve to a Repository"* | *"(HTTP 404)"*) return 1 ;; esac
    return 2
  }
  [ -z "$errf" ] || rm -f "$errf"
  [ -n "$GH_ANSWER" ] || { OWNERSHIP_ERR="gh: empty answer"; return 2; }
}
# Is the repo at URL $1 the login's, judged as itself: a fork is its own
# owner's, not its parent's. A URL off github — a local path, a private host —
# is the user's own experiment, with no outward gate.
url_is_owned() {
  local slug
  slug=$(github_slug "$1") || return 0
  OWNERSHIP_REPO=$slug
  cached_owned "$slug" && return 0
  gh_login || return 2
  gh_repo "$1" '.owner.login + "/" + .name' || return
  ieq "${GH_ANSWER%%/*}" "$GH_LOGIN" || return 1
  cache_owned "$slug"
  return 0
}
# Is the PR base the repo at URL $1 resolves to the login's: its parent when
# it is a fork, else itself. The URL is named to gh explicitly (a bare `gh
# repo view` would resolve to an `upstream` remote instead). base/<key of $1>
# is written only once that base is verified owned, so its presence is the
# verdict.
base_is_owned() {
  local slug map
  slug=$(github_slug "$1") || return 0
  OWNERSHIP_REPO=$slug
  map="$cache_dir/base/$(cache_key "$slug")"
  [ -f "$map" ] && return 0
  gh_login || return 2
  gh_repo "$1" 'if .isFork then (.parent.owner.login + "/" + .parent.name) else (.owner.login + "/" + .name) end' || return
  OWNERSHIP_REPO=$GH_ANSWER
  ieq "${GH_ANSWER%%/*}" "$GH_LOGIN" || return 1
  mkdir -p "$cache_dir/base" 2>/dev/null && printf '%s\n' "$GH_ANSWER" > "$map" 2>/dev/null
  return 0
}
# This checkout's origin, as a merge judges it: 2 outside a checkout. The
# standalone fork of WORKFLOW.md § Gate 1 is judged as itself (#1716); its
# verdict is the push cache's, keyed on its own slug, so removing the marker
# sends the next merge back to the parent.
origin_base_is_owned() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || { OWNERSHIP_ERR="not inside a git checkout"; return 2; }
  if [ "$(git config --get remote.origin.gh-resolved 2>/dev/null)" = base ]; then
    url_is_owned "$(git remote get-url origin 2>/dev/null)"
    return
  fi
  base_is_owned "$(git remote get-url origin 2>/dev/null)"
}

# Does the command run a line matching the regex $1, as a command and not as
# text an argument carries? `pr_settle.py ... --merge` is a `gh pr merge` run
# in a process this hook does not see (#1526), so its command line is read as
# one. `gh pr new` is gh's own alias of `gh pr create`, and gh takes the
# repo flag between `pr` and the verb too.
merge_re='(gh[[:space:]]+pr[[:space:]]+merge|[^[:space:];&|]*pr_settle\.py[^;&|]*[[:space:]]--merge)([[:space:]]|$)'
create_re='gh[[:space:]]+pr[[:space:]]+((-R|--repo)([[:space:]]+|=)[^[:space:]]+[[:space:]]+)?(create|new)([[:space:]]|$)'
runs_gh() {
  # Cheap gate on the raw command (heredoc bodies included) before the lexer.
  printf '%s\n' "$COMMAND" | grep -qE "$1" || return 1
  quote_views "$SCAN"
  printf '%s\n' "$BARE" | grep -qE "$cmd_start$1" && return 0
  printf '%s\n' "$EXPANDS" | grep -qE "(\\\$\\(|\`)[[:space:]]*$1" && return 0
  # A shell handed text: `sh -c`, `eval`, a pipe or a heredoc into a shell.
  printf '%s\n' "$BARE" | grep -qE "$shell_handed"
}
# Owners the text $1 names: `--repo`/`-R` values ([HOST/]OWNER/REPO),
# GH_REPO=, and PR URLs, read with quotes dropped so a quoted value counts. A
# value led by `/`, `~` or `.`, or outside two-to-three segments, is not a
# repo name (e.g. `merge-cleanup --repo <path>`) and names no owner (#803).
# OWNER is the first segment, or the second when a HOST leads. A URL
# (`https://`, `ssh://git@`) loses its scheme, and its OWNER is the segment
# after the host (a `user@` rides along in the host); one with no OWNER prints
# `?`, which never matches the login, so it fails closed. The scp form
# `user@host:OWNER/REPO` (#805) carries no scheme, so it never hits the URL
# rule above and needs its own: only a clean host:OWNER/REPO reads OWNER out;
# anything else with that '@...:' shape prints '?' and fails closed, rather
# than being dropped as "not a repo name" the way a bare path is.
named_owners() {
  printf '%s\n' "$1" | tr -d "'\"" \
    | grep -oE '(--repo[= ]|-R[[:space:]]+|GH_REPO=)[^[:space:];&|)]+' \
    | sed -E 's/^(--repo[= ]|-R[[:space:]]+|GH_REPO=)//' \
    | awk -F/ '
        sub(/^[A-Za-z][A-Za-z0-9+.-]*:\/\//, "") { print ($2 != "" ? $2 : "?"); next }
        $1 ~ /@[^\/]*:/ {
          owner = $1; sub(/^[^:]*:/, "", owner)
          print (owner != "" && NF == 2 ? owner : "?"); next
        }
        !/^[\/~.]/ && NF >= 2 && NF <= 3 { print (NF == 3 ? $2 : $1) }'
  printf '%s\n' "$1" | grep -oE 'github\.com/[^/[:space:]]+/[^/[:space:]]+/pull/' \
    | cut -d/ -f2
}
# Every owner in the list $1 is the login; 2, naming them, when the login
# cannot be read.
owners_are_login() {
  local owner
  OWNERSHIP_REPO="the repo the command names (owner $(printf '%s' "$1" | paste -sd, -))"
  gh_login || return 2
  while IFS= read -r owner; do
    ieq "$owner" "$GH_LOGIN" || return 1
  done <<< "$1"
}
# A name found anywhere in the command is checked on top of what the command
# acts on, never instead of it, so a name on another command or inside a
# quoted subject can only block. Read from the whole command, heredoc bodies
# included when a shell is handed the text.
command_owners_are_login() {
  local owners text=$SCAN
  command_views
  [ "$cmd_handed" = 1 ] && text=$COMMAND
  owners=$(named_owners "$text")
  [ -z "$owners" ] || owners_are_login "$owners"
}
# Returns as base_is_owned does: 0 owned, 1 not owned, 2 gh could not answer.
merge_is_owned() {
  origin_base_is_owned || return
  # The checkout is already verified; what is left unread is the named repo.
  command_owners_are_login
}
# Every repo gh could take as a PR's default base: each github remote as
# itself and, when it is a fork, its parent, plus a repo `gh repo set-default`
# names outright. gh orders the remotes (`upstream`, `github`, `origin`) and
# honours set-default, so judging them all blocks whatever it picks. Outside a
# checkout gh has no default, so 2.
default_bases_are_owned() {
  local url
  git rev-parse --git-dir >/dev/null 2>&1 || { OWNERSHIP_ERR="not inside a git checkout"; return 2; }
  while IFS= read -r url; do
    url_is_owned "$url" || return
    base_is_owned "$url" || return
  done < <(git remote -v | awk '$3 == "(fetch)" { print $2 }'
           git config --get-regexp '^remote\..*\.gh-resolved$' | awk '$2 ~ /\// { print "https://github.com/" $2 }')
}
# The base of a `gh pr create`: every repo the command names must be the
# login's, and unless each create the shell runs names its repo itself,
# unquoted, gh's default base must be too. 3, PR_WHY saying why, when the
# default base is read from a checkout a `cd` moved away from.
pr_create_is_owned() {
  local segment segments
  command_owners_are_login || return
  command_views
  segments=$(split_segments "$CMD_BARE" | grep -E "$create_re")
  if [ -n "$segments" ]; then
    while IFS= read -r segment; do
      [ -n "$(named_owners "$segment")" ] || { segments=""; break; }
    done <<< "$segments"
  fi
  [ -n "$segments" ] && return 0
  PR_WHY="a cd or pushd in the command, so gh picks the base in a checkout this guard cannot read"
  echo "$SCAN" | grep -qE "$cd_re" && return 3
  default_bases_are_owned
}
# The two block texts every policy shares: ownership unreadable (rc 2), and
# the gh answer behind a not-owned verdict on a repo gh cannot see.
lookup_blocked() { # <what the command does, as a lead-in, or empty>
  echo "BLOCKED: $1could not verify ownership of ${OWNERSHIP_REPO:-this checkout} (${OWNERSHIP_ERR:-no error text}) — retry once it can be verified. This is a lookup failure, not a foreign repo." >&2
}
unseen_note() {
  [ -z "$OWNERSHIP_ERR" ] || printf ' (%s — if it is yours, the gh token cannot see it.)' "$OWNERSHIP_ERR"
}

# --- PR merge policy: your repo = allowed, anyone else's = handed off. ---
if runs_gh "$merge_re"; then
  merge_is_owned; rc=$?
  if [ "$rc" = 2 ]; then
    lookup_blocked "'$COMMAND' merges a PR; "
    exit 2
  elif [ "$rc" != 0 ]; then
    echo "BLOCKED: '$COMMAND' merges a PR on a repo you don't own.$(unseen_note) That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! gh pr merge ...' line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
fi

# --- PR create policy: a PR whose base is yours = allowed, else handed off. ---
if runs_gh "$create_re"; then
  OWNERSHIP_ERR="" OWNERSHIP_REPO=""
  pr_create_is_owned; rc=$?
  if [ "$rc" = 2 ]; then
    lookup_blocked "'$COMMAND' opens a PR; "
    exit 2
  elif [ "$rc" = 3 ]; then
    echo "BLOCKED: '$COMMAND' opens a PR, and this guard cannot tell its base ($PR_WHY). Run it from the checkout itself with '--repo <owner>/<name>' unquoted on the 'gh pr create', or hand the user the exact '! gh pr create ...' line." >&2
    exit 2
  elif [ "$rc" != 0 ]; then
    echo "BLOCKED: '$COMMAND' opens a PR on $OWNERSHIP_REPO, a repo you don't own.$(unseen_note) That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! gh pr create --repo <base> --head <owner>:<branch> --title ... --body ...' line, title and body drafted, to run in their own shell. Do not attempt it yourself." >&2
    exit 2
  fi
fi

# --- Push policy: judged by the repo each push is sent to. ---
# The repository a push segment $1 names, into PUSH_WORD (empty when none):
# the first word after `push` that is not an option, an option's value or a
# redirection, or the value of `--repo`. Quotes and parentheses are dropped,
# so a quoted remote name counts; an `&` ends the command.
push_named_remote() {
  local w words after=0 skip=0 repo_next=0 stop
  PUSH_WORD=""
  set -f
  read -r -a words <<< "$(printf '%s' "$1" | tr -d "'\"()")"
  set +f
  for w in "${words[@]}"; do
    if [ "$after" = 0 ]; then [ "$w" = push ] && after=1; continue; fi
    [ "$skip" = 1 ] && { skip=0; continue; }
    case "$w" in
      *'<' | *'>') skip=1; continue ;;
      *'<'* | *'>'*) continue ;;
    esac
    stop=0
    case "$w" in *'&'*) w=${w%%&*}; stop=1 ;; esac
    if [ -n "$w" ]; then
      [ "$repo_next" = 1 ] && { PUSH_WORD=$w; return; }
      case "$w" in
        --repo=*) PUSH_WORD=${w#--repo=}; return ;;
        --repo) repo_next=1 ;;
        -o | --push-option | --receive-pack | --exec) skip=1 ;;
        -*) ;;
        *) PUSH_WORD=$w; return ;;
      esac
    fi
    [ "$stop" = 1 ] && return
  done
}
# The URLs a push segment $1 sends to, one per line, into PUSH_URLS. The
# remote is the one the command names, else the branch's pushRemote,
# remote.pushDefault, the branch's remote, then origin: git's own order. It is
# read in the checkout `git_target` resolves, so a `cd`, a comment or a
# GIT_DIR is refused, not guessed at. PUSH_REMOTE is the remote's name when it
# is a configured one, for the block text; a URL the command spells out is
# never printed, as it can carry a token. 3, PUSH_WHY saying why, when the
# target cannot be told.
push_target() {
  local dir branch
  OWNERSHIP_ERR="" OWNERSHIP_REPO="" PUSH_REMOTE=""
  git_target "$1" || { PUSH_WHY=$TARGET_WHY; return 3; }
  dir=$TARGET_TOP
  push_named_remote "$1"
  case "$PUSH_WORD" in *'$'* | *'`'*) PUSH_WHY="the remote is a shell expansion, '$PUSH_WORD'"; return 3 ;; esac
  if [ -z "$PUSH_WORD" ]; then
    branch=$(git -C "$dir" symbolic-ref -q --short HEAD)
    [ -n "$branch" ] && PUSH_WORD=$(git -C "$dir" config "branch.$branch.pushRemote")
    [ -n "$PUSH_WORD" ] || PUSH_WORD=$(git -C "$dir" config remote.pushDefault)
    [ -n "$PUSH_WORD" ] || [ -z "$branch" ] || PUSH_WORD=$(git -C "$dir" config "branch.$branch.remote")
    PUSH_WORD=${PUSH_WORD:-origin}
  fi
  if PUSH_URLS=$(git -C "$dir" remote get-url --push --all "$PUSH_WORD" 2>/dev/null); then
    PUSH_REMOTE=$PUSH_WORD
    return 0
  fi
  # Not a configured remote: a URL or a path, with `insteadOf` applied the
  # way git applies it. A bare word that is neither is refused.
  case "$PUSH_WORD" in
    . | */* | *:*)
      PUSH_URLS=$(git -C "$dir" ls-remote --get-url "$PUSH_WORD" 2>/dev/null) || PUSH_URLS=$PUSH_WORD ;;
    *) PUSH_WHY="'$PUSH_WORD' is no remote configured in $dir, nor a URL or a path"; return 3 ;;
  esac
}
push_is_owned() { # <segment>
  local url
  push_target "$1" || return
  while IFS= read -r url; do
    url_is_owned "$url" || return
  done <<< "$PUSH_URLS"
}
if echo "$SCAN" | grep -qE "$push_re"; then
  while IFS= read -r segment; do
    push_is_owned "$segment"; rc=$?
    case "$rc" in
      0) continue ;;
      2) lookup_blocked "" ;;
      3) echo "BLOCKED: '$COMMAND' pushes, and this guard cannot tell where to ($PUSH_WHY). Give the push as 'git -C <absolute path> push <remote> <branch>' with a configured remote, and no cd, comment or shell expansion." >&2 ;;
      *) echo "BLOCKED: pushing to a repo you don't own.$(unseen_note) This push goes to $OWNERSHIP_REPO${PUSH_REMOTE:+, through remote '$PUSH_REMOTE'}. Hand the user the exact '! git push -u <remote> <branch>' line and a drafted '! gh pr create ...' line to run in their own shell — the outward-facing step is theirs, not yours." >&2 ;;
    esac
    exit 2
  done < <(split_segments "$SCAN" | grep -E "$push_re")
fi

exit 0
