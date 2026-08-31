#!/bin/bash
# Git guardrails (PreToolUse, Bash).
#
# Two narrow guards; everything else about a push is the agent's business.
#   - PUSH is gated on OWNERSHIP, not on branch or file type. If origin's owner
#     is the `gh` login (resolving a fork to its parent, the way `pushpr` does),
#     every push is allowed — any branch, any content, default branch included.
#     A repo someone else owns is blocked and handed off to `pushpr`, which
#     carries the outward gate (it pushes the branch but leaves the PR to the
#     user). The ownership lookup FAILS CLOSED: gh erroring or the network
#     being down means "not owned" means blocked.
#   - `gh pr merge` is blocked everywhere. When a PR exists, only the user
#     finishes it — via `! gh pr merge ...` in their own shell, or the web UI.
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

# --- Always-blocked: PR merges and history/worktree destroyers. ---
DANGEROUS_PATTERNS=(
  "gh pr merge"
  "git ctm"
  "git-ctm"
  "git reset --hard"
  "reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
)
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$SCAN" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' matches protected pattern '$pattern'. That part is the user's, not yours. HAND OFF: re-run the command without it, then give the user the exact '! $pattern ...' line to run themselves. Do not attempt it yourself." >&2
    exit 2
  fi
done

# --- Bare force-push: blocked. `--force-with-lease` is fine (the lease refuses
# to clobber commits this clone hasn't seen), and still goes through the
# ownership gate below like any other push. ---
if echo "$SCAN" | grep -qE 'push([[:space:]].*)?[[:space:]](--force([[:space:]]|$)|-f([[:space:]]|$))' \
   && ! echo "$SCAN" | grep -q 'force-with-lease'; then
  echo "BLOCKED: bare force-push in '$COMMAND' can destroy commits on origin. Use '--force-with-lease', or hand the user the exact '! git push --force ...' line." >&2
  exit 2
fi

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

  # Same resolution as pushpr: evaluate ORIGIN explicitly (a bare `gh repo
  # view` would resolve to an `upstream` remote instead), and a fork's real
  # base repo is its parent. Any failure here returns non-zero -> blocked.
  me=$(gh api user -q .login 2>/dev/null) || return 1
  target=$(gh repo view "$origin" --json owner,name,isFork,parent \
      -q 'if .isFork then (.parent.owner.login + "/" + .parent.name) else (.owner.login + "/" + .name) end' 2>/dev/null) || return 1
  [ -n "$me" ] && [ -n "$target" ] || return 1
  [ "${target%%/*}" = "$me" ] || return 1

  mkdir -p "$cache_dir" 2>/dev/null && printf '%s\n' "$target" > "$cache_dir/$key" 2>/dev/null
  return 0
}

# --- Push policy: your repo = allowed, anyone else's = handed off. ---
if echo "$SCAN" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)'; then
  if repo_is_owned; then
    exit 0
  fi
  echo "BLOCKED: pushing to a repo you don't own (or ownership couldn't be verified — gh down?). Use 'pushpr': it pushes the branch and stops before the PR, leaving the outward-facing step to the user." >&2
  exit 2
fi

exit 0
