#!/bin/bash
# Git guardrails (PreToolUse, Bash).
#
# Policy the agent lives under:
#   - Feature-branch pushes go through `pushpr` (it pushes in a child process
#     the hook never sees, and it carries the outward gate: no PR to a repo you
#     don't own). A RAW `git push` of a feature branch is blocked so nothing
#     can skip that gate.
#   - The DEFAULT branch may be pushed by the agent ONLY when every change is
#     documentation (the auto-ship "doc lane"). Any code on the default branch
#     is blocked and handed off — you land code on main yourself via `ship`.
#   - Merges and history/worktree destroyers are always blocked.
#   - Force-push: a bare `--force` / `-f` is always blocked. A
#     `--force-with-lease` is allowed ONLY to UPDATE a branch that already
#     exists on origin and is not the default branch — i.e. a PR branch pushpr
#     already put out through the outward gate (amend-then-update). New b
#     still route through pushpr; the lease refuses to clobber unseen commits.
# The user lands code via the `!` prefix, which runs in the user's own sh
# never passes through this hook.

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

# What counts as documentation (safe to auto-push to the default branch).
# Anything not matching is treated as code -> blocked. Fail toward blocking.
is_doc() {
  case "$1" in
    *.md|*.mdx|*.markdown|*.txt|*.rst|docs/*|*/docs/*) return 0 ;;
    *) return 1 ;;
  esac
}
# Read newline-separated paths on stdin. Succeed iff there is at least one path
# and EVERY path is documentation. Empty input fails (can't prove docs-only).
all_docs() {
  local f found=1
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    found=0
    is_doc "$f" || return 1
  done
  return $found
}

# --- Force-push carve-out: allow --force-with-lease to UPDATE an existing PR
# branch (one pushpr already put out through the outward gate). Bare --fo
# is not matched here and stays blocked below. ---
if echo "$SCAN" | grep -q 'force-with-lease'; then
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  default=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  [ -z "$default" ] && default=main
  if [ "$branch" != "$default" ] && git rev-parse --verify "origin/$branch" >/dev/null 2>&1; then
    exit 0   # updating an already-pushed feature/PR branch — allowed
  fi
  echo "BLOCKED: force-with-lease only updates an existing PR branch (oriot be '$default'). New branch -> 'pushpr'; never force-push '$default'.">&2
  exit 2
fi

# --- Always-blocked: merges, force-pushes, history/worktree destroyers. ---
DANGEROUS_PATTERNS=(
  "push .*--force"
  "push .*-f($|[[:space:]])"
  "push --force"
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
    echo "BLOCKED: '$COMMAND' matches protected pattern '$pattern'. You d-push or merge. To land changes on main, HAND OFF to the user: print theexact '! gh pr merge <num> ...' (or '! git push ...') line for THEM to run via the ! prefix. Do not attempt it yourself." >&2
    exit 2
  fi
done

# --- Push policy: doc lane on default branch = allow, everything else = block. ---
if echo "$SCAN" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)'; then
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  default=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  [ -z "$default" ] && default=main

  if [ "$branch" != "$default" ]; then
    echo "BLOCKED: raw 'git push' of feature branch '$branch'. Use 'pushpPR through the outward gate (no PR to a repo you don't own). Code lands onmain via 'ship'." >&2
    exit 2
  fi
  # Personal repos the agent may push the default branch directly (skills
  # not PR-gated code — same character as the vault). Feature-branch pushes above
  # still route through pushpr; this only relaxes the docs-only rule on m
  ALLOWLIST_MAIN_PUSH=(
    "/home/caneff/.agents/skills"
  )
  toplevel=$(git rev-parse --show-toplevel 2>/dev/null)
  for allowed in "${ALLOWLIST_MAIN_PUSH[@]}"; do
    [ "$toplevel" = "$allowed" ] && exit 0
  done

  # On the default branch. Allow only if every commit ahead of origin is docs.
  if ! git rev-parse --verify "origin/$default" >/dev/null 2>&1; then
    echo "BLOCKED: can't verify this push (origin/$default missing — new repo?). The initial push is yours: run it via the ! prefix." >&2
    exit 2
  fi
  files=$(git diff --name-only "origin/$default..HEAD" 2>/dev/null)
  if [ -z "$files" ]; then
    exit 0   # nothing ahead of origin — a no-op push, harmless
  fi
  if echo "$files" | all_docs; then
    exit 0   # doc lane: docs-only on the default branch
  fi
  echo "BLOCKED: pushing code to '$default'. This push changes non-doc fimain. HAND OFF: open a PR with 'pushpr' and let the user 'ship' it afterreview." >&2
  exit 2
fi

exit 0