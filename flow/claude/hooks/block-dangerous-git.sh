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

# A heredoc body is data being written to a file, not a command being run.
# Scanning it for dangerous patterns produces false positives: writing a doc
# that mentions a blocked git verb is harmless, yet the raw grep below would
# block it. Strip heredoc bodies (keeping the opener line, which may carry the
# real command) and scan the result. Detection uses $SCAN; error messages still
# quote the original $COMMAND.
strip_heredocs() {
  local line delim="" indoc=0 trimmed
  local re='<<-?[[:space:]]*["'"'"'`]?([A-Za-z_][A-Za-z0-9_]*)'
  while IFS= read -r line; do
    if [ "$indoc" -eq 1 ]; then
      trimmed="${line#"${line%%[![:space:]]*}"}"
      if [ "$line" = "$delim" ] || [ "$trimmed" = "$delim" ]; then indoc=0; fi
      continue
    fi
    if [[ "$line" =~ $re ]]; then delim="${BASH_REMATCH[1]}"; indoc=1; fi
    printf '%s\n' "$line"
  done
}
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
has_dot_pathspec() { echo "$SCAN" | grep -qE '(^|[[:space:]])\.([[:space:]]|$)'; }
restore_is_unstage_only() {
  echo "$SCAN" | grep -q -- '--staged' && ! echo "$SCAN" | grep -q -- '--worktree'
}
git_verb() {
  echo "$SCAN" | grep -qE "(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+$1([[:space:]]|\$)"
}

if has_dot_pathspec && { git_verb checkout || { git_verb restore && ! restore_is_unstage_only; }; }; then
  echo "BLOCKED: '$COMMAND' discards every uncommitted change under '.'. That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact line to run themselves. Do not attempt it yourself." >&2
  exit 2
fi

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

# --- Ownership of this repo, cached. ---
# Verdict is keyed on the repo's toplevel path. Only the OWNED verdict is
# cached: it's the hot path (allow), so caching it keeps `gh` off every
# subsequent Bash call, while a not-owned/lookup-failed verdict is never
# written — a block is rare, so re-asking costs nothing and a stale "no" (or a
# cached network blip) can never harden into a permanent block. Delete
# $cache_dir if a repo's origin changes hands.
repo_is_owned() {
  local toplevel origin cache_dir key me target
  toplevel=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
  origin=$(git remote get-url origin 2>/dev/null)

  # Non-github origins — a local path, a private host, or no remote at all —
  # are the user's own experiments. There is no outward gate to enforce.
  case "$origin" in
    *github.com*) ;;
    *) return 0 ;;
  esac

  cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-git-guard"
  key=$(printf '%s' "$toplevel" | tr -c 'A-Za-z0-9' '_')
  [ -f "$cache_dir/$key" ] && return 0

  # Evaluate ORIGIN explicitly (a bare `gh repo view` would resolve to an
  # `upstream` remote instead), and a fork's real base repo is its parent.
  # Any failure here returns non-zero -> blocked.
  me=$(gh api user -q .login 2>/dev/null) || return 1
  target=$(gh repo view "$origin" --json owner,name,isFork,parent \
      -q 'if .isFork then (.parent.owner.login + "/" + .parent.name) else (.owner.login + "/" + .name) end' 2>/dev/null) || return 1
  [ -n "$me" ] && [ -n "$target" ] || return 1
  [ "${target%%/*}" = "$me" ] || return 1

  mkdir -p "$cache_dir" 2>/dev/null && printf '%s\n' "$target" > "$cache_dir/$key" 2>/dev/null
  return 0
}

# --- PR merge policy: your repo = allowed, anyone else's = handed off. ---
merge_re='gh[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)'
cmd_start='(^|[;&|(`[:space:]])'
# Two views of $1 from one pass that tracks quoting: BARE drops every quoted
# character (what the shell runs as words); EXPANDS drops only single-quoted
# ones, since `$(...)` and backticks still run inside double quotes.
quote_views() {
  local s=$1 i c q="" bare="" exp=""
  for ((i = 0; i < ${#s}; i++)); do
    c=${s:i:1}
    case "$q" in
      "'") [ "$c" = "'" ] && q="" ;;
      '"')
        if [ "$c" = '\' ]; then exp+=$c${s:i+1:1}; i=$((i + 1))
        elif [ "$c" = '"' ]; then q=""
        else exp+=$c; fi ;;
      *)
        case "$c" in
          "'" | '"') q=$c ;;
          '\') bare+=$c${s:i+1:1}; exp+=$c${s:i+1:1}; i=$((i + 1)) ;;
          *) bare+=$c; exp+=$c ;;
        esac ;;
    esac
  done
  BARE=$bare EXPANDS=$exp
}
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
# rule above; its OWNER sits after the ':' in the first slash-segment, not in
# the whole 'host:owner' chunk that segment naively splits out to. Only a
# clean host:OWNER/REPO (one slash total) is read; anything else with that
# '@...:' shape prints '?' and fails closed rather than being dropped as "not
# a repo name" the way a bare path is.
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
merge_is_owned() {
  local owners me owner
  repo_is_owned || return 1
  owners=$(named_merge_owners)
  [ -n "$owners" ] || return 0
  me=$(gh api user -q .login 2>/dev/null) || return 1
  [ -n "$me" ] || return 1
  while IFS= read -r owner; do
    [ "$owner" = "$me" ] || return 1
  done <<< "$owners"
}
if runs_pr_merge && ! merge_is_owned; then
  echo "BLOCKED: '$COMMAND' merges a PR on a repo you don't own (or ownership couldn't be verified — gh down?). That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! gh pr merge ...' line to run themselves. Do not attempt it yourself." >&2
  exit 2
fi

# --- Push policy: your repo = allowed, anyone else's = handed off. ---
if echo "$SCAN" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)'; then
  if repo_is_owned; then
    exit 0
  fi
  echo "BLOCKED: pushing to a repo you don't own (or ownership couldn't be verified — gh down?). Hand the user the exact '! git push -u origin <branch>' line and a drafted 'gh pr create' line to run in their own shell — the outward-facing step is theirs, not yours." >&2
  exit 2
fi

exit 0
