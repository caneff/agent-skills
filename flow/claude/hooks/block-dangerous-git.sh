#!/bin/bash
# Git guardrails (PreToolUse, Bash).
#
# Narrow guards; everything else about a push is the agent's business.
#   - PUSH is gated on OWNERSHIP, not on branch or file type. If origin's owner
#     is the `gh` login (resolving a fork to its parent), every push is allowed
#     — any branch, any content, default branch included. A repo someone else
#     owns is blocked, and the agent hands the user the push and PR lines to
#     run themselves: the outward-facing step is the user's. The ownership
#     lookup FAILS CLOSED: gh erroring or the network being down means "not
#     owned" means blocked.
#   - `gh pr merge` (and `implement/pr_settle.py ... --merge`, which runs one,
#     #1526) is gated on the same OWNERSHIP (#790): allowed when this
#     checkout and every repo the line names are the `gh` login's, blocked
#     everywhere else. Only the command is matched, not the phrase: quoted
#     text (a grep pattern, a commit message) is data unless a shell runs
#     it. The `ready-for-human` exception —
#     the user merges that ticket's PR — is enforced by `/implement`'s prose,
#     not here: a squash merge on the user's own repo is undone with a revert,
#     so a prose miss there costs a revert, not a merge nobody can take back.
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
command_views() {
  [ -n "${CMD_VIEWS_DONE:-}" ] && return 0
  CMD_VIEWS_DONE=1
  quote_views "$SCAN"
  CMD_BARE=$BARE
  CMD_EXPANDS=$EXPANDS
  cmd_handed=0
  printf '%s\n' "$CMD_BARE" | grep -qE "$shell_handed" && cmd_handed=1
  cmd_substitutions=$(printf '%s' "$CMD_EXPANDS" | tr '\n' ' ' | grep -oE '\$\(.*\)|`[^`]*`')
  return 0
}

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
  echo "$SCAN" | grep -qE '(^|[;&|(`[:space:]])(cd|pushd)([[:space:]]|$)' && return 1
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
done < <(printf '%s\n' "$SCAN" | sed -E 's/(&&|\|\||;|\|)/\n/g' | grep -e checkout -e restore)

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
  done < <(printf '%s\n' "$SCAN" | sed -E 's/(&&|\|\||;|\|)/\n/g' | grep stash)
fi

# --- Bare force-push: blocked. `--force-with-lease` is fine (the lease refuses
# to clobber commits this clone hasn't seen), and still goes through the
# ownership gate below like any other push. Judged per command segment: a
# `--force` that belongs to another command in the chain (`worktree rm
# --force`) or a `push` that is only a word in a path (`hooks/pre-push`) is
# not a force-push (#637). ---
is_force_push_segment() {
  echo "$1" | grep -qE '(^|[[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)' \
    && echo "$1" | grep -qE '[[:space:]](--force([[:space:]]|$)|-f([[:space:]]|$))' \
    && ! echo "$1" | grep -q 'force-with-lease'
}
while IFS= read -r segment; do
  if is_force_push_segment "$segment"; then
    echo "BLOCKED: bare force-push in '$COMMAND' can destroy commits on origin. Use '--force-with-lease', or hand the user the exact '! git push --force ...' line." >&2
    exit 2
  fi
done < <(printf '%s\n' "$SCAN" | sed -E 's/(&&|\|\||;|\|)/\n/g' | grep -e push)

# GitHub owners are case-insensitive: `CANEFF/x` and `caneff/x` name the same
# account, so every owner-vs-login compare lowercases both sides first. `tr`
# over bash's `${,,}`: GitHub logins are ASCII, and `${,,}` folds by locale
# (a Turkish locale maps `I` to dotless `ı`, not `i`), which could turn a
# same-account match into a false block.
ieq() { [ "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" = "$(printf '%s' "$2" | tr 'A-Z' 'a-z')" ]; }

# --- Ownership of this repo, cached. ---
# Verdict is keyed on the origin URL, normalised to owner/name, so a verdict
# earned once covers every worktree of the repo and a fresh `implement-*`
# worktree never re-asks gh. Only the OWNED verdict is cached: it's the hot
# path (allow), so caching it keeps `gh` off every subsequent Bash call, while
# a not-owned/lookup-failed verdict is never written — a block is rare, so
# re-asking costs nothing and a stale "no" (or a cached network blip) can
# never harden into a permanent block. Delete $cache_dir if a repo's origin
# changes hands.
# Returns 0 owned, 1 not owned (gh answered, a repo this login cannot see
# included), 2 ownership could not be read (gh failed, or no checkout); on 2,
# OWNERSHIP_ERR says why, gh's own error text included, so the block can say
# it was a blip. On a repo gh cannot see, OWNERSHIP_ERR holds gh's answer.
OWNERSHIP_ERR=""
OWNERSHIP_ORIGIN=""
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
repo_is_owned() {
  local toplevel origin cache_dir key target errf slug
  toplevel=$(git rev-parse --show-toplevel 2>/dev/null) || { OWNERSHIP_ERR="not inside a git checkout"; return 2; }
  origin=$(git remote get-url origin 2>/dev/null)

  # Non-github origins — a local path, a private host, or no remote at all —
  # are the user's own experiments. There is no outward gate to enforce.
  case "$origin" in
    *github.com*) ;;
    *) return 0 ;;
  esac

  # https://github.com/o/n.git, git@github.com:o/n.git and ssh://git@github.com/o/n
  # all name the same repo.
  slug=${origin#*github.com}
  slug=${slug#[:/]}; slug=${slug%/}; slug=${slug%.git}
  # The block text names the slug, never the URL: an origin can carry a token.
  OWNERSHIP_ORIGIN=$slug
  cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-git-guard"
  # `/` becomes `@`, which GitHub names cannot hold, so `a-b/c` and `a/b-c`
  # never share a key.
  key=$(printf '%s' "$slug" | tr 'A-Z' 'a-z' | tr '/' '@' | tr -c 'a-z0-9@._-' '_')
  [ -f "$cache_dir/$key" ] && return 0

  # Evaluate ORIGIN explicitly (a bare `gh repo view` would resolve to an
  # `upstream` remote instead), and a fork's real base repo is its parent.
  # gh's own error text goes to a temp file; with no temp file the block says so.
  gh_login || return 2
  errf=$(mktemp 2>/dev/null) || errf=""
  target=$(gh repo view "$origin" --json owner,name,isFork,parent \
      -q 'if .isFork then (.parent.owner.login + "/" + .parent.name) else (.owner.login + "/" + .name) end' 2>"${errf:-/dev/null}") || {
    gh_failed "$errf"
    # gh reached GitHub and was told the repo does not exist for this login.
    case "$OWNERSHIP_ERR" in *"Could not resolve to a Repository"* | *"(HTTP 404)"*) return 1 ;; esac
    return 2
  }
  [ -z "$errf" ] || rm -f "$errf"
  [ -n "$target" ] || { OWNERSHIP_ERR="gh: empty answer"; return 2; }
  ieq "${target%%/*}" "$GH_LOGIN" || return 1

  mkdir -p "$cache_dir" 2>/dev/null && printf '%s\n' "$target" > "$cache_dir/$key" 2>/dev/null
  return 0
}

# --- PR merge policy: your repo = allowed, anyone else's = handed off. ---
# `pr_settle.py ... --merge` is a `gh pr merge` run in a process this hook does
# not see (#1526), so its command line is read as one.
merge_re='(gh[[:space:]]+pr[[:space:]]+merge|[^[:space:];&|]*pr_settle\.py[^;&|]*[[:space:]]--merge)([[:space:]]|$)'
runs_pr_merge() {
  # Cheap gate on the raw command (heredoc bodies included) before the lexer.
  printf '%s\n' "$COMMAND" | grep -qE "$merge_re" || return 1
  quote_views "$SCAN"
  printf '%s\n' "$BARE" | grep -qE "$cmd_start$merge_re" && return 0
  printf '%s\n' "$EXPANDS" | grep -qE "(\\\$\\(|\`)[[:space:]]*$merge_re" && return 0
  # A shell handed text: `sh -c`, `eval`, a pipe or a heredoc into a shell.
  printf '%s\n' "$BARE" | grep -qE "$shell_handed"
}
# Owners the line names: `--repo`/`-R` values ([HOST/]OWNER/REPO), GH_REPO=,
# and PR URLs, read from the raw text so a quoted value counts. A value led by
# `/`, `~` or `.`, or outside two-to-three segments, is not a repo name (e.g.
# `merge-cleanup --repo <path>`) and names no owner (#803). OWNER is the first
# segment, or the second when a HOST leads. A URL (`https://`, `ssh://git@`)
# loses its scheme, and its OWNER is the segment after the host (a `user@`
# rides along in the host); one with no OWNER prints `?`, which never matches
# the login, so it fails closed. They are
# checked on top of this checkout's ownership, never instead of it, so a name
# on another command or inside a quoted subject can only block. The scp form
# `user@host:OWNER/REPO` (#805) carries no scheme, so it never hits the URL
# rule above and needs its own: only a clean host:OWNER/REPO reads OWNER out;
# anything else with that '@...:' shape prints '?' and fails closed, rather
# than being dropped as "not a repo name" the way a bare path is.
named_merge_owners() {
  printf '%s\n' "$SCAN" | tr -d "'\"" \
    | grep -oE '(--repo[= ]|-R[[:space:]]+|GH_REPO=)[^[:space:];&|)]+' \
    | sed -E 's/^(--repo[= ]|-R[[:space:]]+|GH_REPO=)//' \
    | awk -F/ '
        sub(/^[A-Za-z][A-Za-z0-9+.-]*:\/\//, "") { print ($2 != "" ? $2 : "?"); next }
        $1 ~ /@[^\/]*:/ {
          owner = $1; sub(/^[^:]*:/, "", owner)
          print (owner != "" && NF == 2 ? owner : "?"); next
        }
        !/^[\/~.]/ && NF >= 2 && NF <= 3 { print (NF == 3 ? $2 : $1) }'
  printf '%s\n' "$SCAN" | grep -oE 'github\.com/[^/[:space:]]+/[^/[:space:]]+/pull/' \
    | cut -d/ -f2
}
# Returns as repo_is_owned does: 0 owned, 1 not owned, 2 gh could not answer.
merge_is_owned() {
  local owners owner rc
  repo_is_owned; rc=$?
  [ "$rc" = 0 ] || return "$rc"
  owners=$(named_merge_owners)
  [ -n "$owners" ] || return 0
  # The checkout is already verified; what is left unread is the named repo.
  gh_login || { OWNERSHIP_ORIGIN="the repo the command names (owner $(printf '%s' "$owners" | paste -sd, -))"; return 2; }
  while IFS= read -r owner; do
    ieq "$owner" "$GH_LOGIN" || return 1
  done <<< "$owners"
}
# The two block texts both policies share: ownership unreadable (rc 2), and
# the gh answer behind a not-owned verdict on a repo gh cannot see.
lookup_blocked() { # <what the command does, as a lead-in, or empty>
  echo "BLOCKED: $1could not verify ownership of ${OWNERSHIP_ORIGIN:-this checkout} (${OWNERSHIP_ERR:-no error text}) — retry once it can be verified. This is a lookup failure, not a foreign repo." >&2
}
unseen_note() {
  [ -z "$OWNERSHIP_ERR" ] || printf ' (%s — if it is yours, the gh token cannot see it.)' "$OWNERSHIP_ERR"
}
if runs_pr_merge; then
  merge_is_owned; rc=$?
  if [ "$rc" = 2 ]; then
    lookup_blocked "'$COMMAND' merges a PR; "
    exit 2
  elif [ "$rc" != 0 ]; then
    echo "BLOCKED: '$COMMAND' merges a PR on a repo you don't own.$(unseen_note) That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! gh pr merge ...' line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
fi

# --- Push policy: your repo = allowed, anyone else's = handed off. ---
if echo "$SCAN" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)'; then
  repo_is_owned; rc=$?
  [ "$rc" = 0 ] && exit 0
  if [ "$rc" = 2 ]; then
    lookup_blocked ""
    exit 2
  fi
  echo "BLOCKED: pushing to a repo you don't own.$(unseen_note) Hand the user the exact '! git push -u origin <branch>' line and a drafted 'gh pr create' line to run in their own shell — the outward-facing step is theirs, not yours." >&2
  exit 2
fi

exit 0
