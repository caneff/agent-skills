#!/bin/bash
# Git guardrails (PreToolUse, Bash).
#
# Two narrow guards; everything else about a push is the agent's business.
#   - PUSH is gated on OWNERSHIP, not on branch or file type. If origin's owner
#     is the `gh` login (resolving a fork to its parent), every push is allowed
#     — any branch, any content, default branch included. A repo someone else
#     owns is blocked, and the agent hands the user the push and PR lines to
#     run themselves: the outward-facing step is the user's. The ownership
#     lookup FAILS CLOSED: gh erroring or the network being down means "not
#     owned" means blocked.
#   - `gh pr merge` is gated on the same OWNERSHIP (#790): allowed when this
#     checkout and every repo the line names are the `gh` login's, blocked
#     everywhere else. Only the command is matched, not the phrase: quoted
#     text (a grep pattern, a commit message) is data unless a shell runs
#     it. The `ready-for-human` exception —
#     the user merges that ticket's PR — is enforced by `/implement`'s prose,
#     not here: a squash merge on the user's own repo is undone with a revert,
#     so a prose miss there costs a revert, not a merge nobody can take back.
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
# Each is judged on one command segment ($1), so a chain is blocked when any
# one of its discards is.
has_dot_pathspec() { echo "$1" | grep -qE '(^|[[:space:]])\.([[:space:]]|$)'; }
restore_is_unstage_only() {
  echo "$1" | grep -q -- '--staged' && ! echo "$1" | grep -q -- '--worktree'
}
git_verb() {
  echo "$2" | grep -qE "(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+$1([[:space:]]|\$)"
}
# A discard aimed at a linked worktree under `.scratch/mutation-*` is the
# point of that worktree (#1387): a disposable copy a reviewer or worker
# plants one mutation in. The target is `git -C <path>` or the cwd, resolved
# with realpath so a `..` or a symlink cannot name the primary checkout, and
# it must be a linked worktree (git-dir differs from the common dir), so a
# plain directory that only carries the name is not one.
is_mutation_worktree() {
  local dir real gitdir common
  dir=$(echo "$1" | sed -nE 's/.*(^|[;&|[:space:]])git[[:space:]]+-C[[:space:]]+([^[:space:]]+).*/\2/p')
  dir=$(printf '%s' "${dir:-.}" | tr -d "'\"")
  real=$(realpath -- "$dir" 2>/dev/null) || return 1
  case "$real" in */.scratch/mutation-*) ;; *) return 1 ;; esac
  gitdir=$(git -C "$real" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  common=$(git -C "$real" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 1
  [ "$gitdir" != "$common" ]
}
discards_worktree() {
  has_dot_pathspec "$1" || return 1
  git_verb checkout "$1" || { git_verb restore "$1" && ! restore_is_unstage_only "$1"; } || return 1
  ! is_mutation_worktree "$1"
}
while IFS= read -r segment; do
  if discards_worktree "$segment"; then
    echo "BLOCKED: '$COMMAND' discards every uncommitted change under '.'. That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
done < <(printf '%s\n' "$SCAN" | sed -E 's/(&&|\|\||;|\|)/\n/g')

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$SCAN" | grep -qE "$pattern"; then
    hint=""
    [ "$pattern" = "git branch -D" ] && hint=" FIRST try 'git branch -d' (lowercase), which is allowed: git itself refuses it on an unmerged branch, so it deletes the safe ones and needs no hand-off. Hand off only what -d refuses."
    echo "BLOCKED: '$COMMAND' matches protected pattern '$pattern'. That part is the user's, not yours.${hint} HAND OFF: re-run the command without it, then give the user the exact '! $pattern ...' line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
done

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
done < <(printf '%s\n' "$SCAN" | sed -E 's/(&&|\|\||;|\|)/\n/g')

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
merge_re='gh[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)'
cmd_start='(^|[;&|(`[:space:]])'
runs_pr_merge() {
  # Cheap gate on the raw command (heredoc bodies included) before the lexer.
  printf '%s\n' "$COMMAND" | grep -qE "$merge_re" || return 1
  quote_views "$SCAN"
  printf '%s\n' "$BARE" | grep -qE "$cmd_start$merge_re" && return 0
  printf '%s\n' "$EXPANDS" | grep -qE "(\\\$\\(|\`)[[:space:]]*$merge_re" && return 0
  # A shell handed text: `sh -c`, `eval`, a pipe or a heredoc into a shell.
  printf '%s\n' "$BARE" | grep -qE "$cmd_start((bash|sh|zsh)[[:space:]]+-[a-z]*c|eval)([[:space:]]|$)|\|[[:space:]]*(bash|sh|zsh)([[:space:]]|$)|(bash|sh|zsh)[[:space:]]*<<"
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
