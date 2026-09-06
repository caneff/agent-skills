#!/usr/bin/env bash
# skills-sync — report (and optionally repair) drift between two skill dirs:
#   ~/.agents/skills  canonical real bodies
#   ~/.claude/skills  symlinks -> ../../.agents/skills/<name>
#
# Usage: skills-sync.sh [--fix] [--self-test]
# Dirs are overridable via AGENTS/CLAUDE env (used by --self-test).
set -euo pipefail
shopt -s nullglob

: "${AGENTS:=$HOME/.agents/skills}"
: "${CLAUDE:=$HOME/.claude/skills}"

is_skill() { [ -d "$1" ] && [ -f "$1/SKILL.md" ]; }

scan() {
  local fix="$1" d n want tgt
  # claude/ entries: the load-bearing pattern. Must be a symlink -> ../../.agents/skills/<n>
  for d in "$CLAUDE"/*; do
    n=$(basename "$d"); want="../../.agents/skills/$n"
    if [ -L "$d" ]; then
      if [ ! -e "$d/SKILL.md" ]; then
        echo "BROKEN_LINK $n"
        if [ "$fix" = fix ]; then
          if [ -d "$AGENTS/$n" ]; then
            ln -sfn "$want" "$d"
          else
            # no body to point at — prune the dead symlink (only ever a symlink here)
            rm "$d"; echo "  removed dead link $n" >&2
          fi
        fi
        continue
      fi
      tgt=$(readlink "$d")
      if [ "$tgt" != "$want" ]; then
        echo "WRONG_TARGET $n ($tgt)"
        [ "$fix" = fix ] && ln -sfn "$want" "$d"
      fi
    elif is_skill "$d"; then
      echo "NOT_SYMLINK $n"
      if [ "$fix" = fix ]; then
        # ponytail: refuse if a canonical body already exists — moving would clobber it
        if [ -e "$AGENTS/$n" ]; then
          echo "  skip-fix $n: $AGENTS/$n already exists, resolve by hand" >&2
        else
          mv "$d" "$AGENTS/$n"; ln -s "$want" "$d"
        fi
      fi
    fi
  done

  # agents/ bodies with no claude symlink
  for d in "$AGENTS"/*; do
    is_skill "$d" || continue; n=$(basename "$d")
    if [ ! -e "$CLAUDE/$n" ] && [ ! -L "$CLAUDE/$n" ]; then
      echo "NO_SYMLINK $n"
      [ "$fix" = fix ] && ln -s "../../.agents/skills/$n" "$CLAUDE/$n"
    fi
  done
}

self_test() {
  local T; T=$(mktemp -d)
  export AGENTS="$T/.agents/skills" CLAUDE="$T/.claude/skills"
  mkdir -p "$AGENTS" "$CLAUDE"
  mk() { mkdir -p "$1"; echo 'name: x' > "$1/SKILL.md"; }

  # clean: body + correct symlink (should produce nothing)
  mk "$AGENTS/ok";   ln -s "../../.agents/skills/ok" "$CLAUDE/ok"
  # NO_SYMLINK: body, no claude link
  mk "$AGENTS/nolink"
  # NOT_SYMLINK: real dir in claude, no agents body
  mk "$CLAUDE/realdir"
  # WRONG_TARGET: symlink resolves (target has SKILL.md) but points at the wrong body
  mk "$AGENTS/wrong"; ln -s "../../.agents/skills/ok" "$CLAUDE/wrong"
  # BROKEN_LINK: claude link to missing body
  ln -s "../../.agents/skills/dead" "$CLAUDE/dead"

  local out; out=$(scan nofix)
  local fail=0
  check() { grep -q "^$1\$" <<<"$out" || { echo "FAIL: expected '$1'"; fail=1; }; }
  check "NO_SYMLINK nolink"
  check "NOT_SYMLINK realdir"
  check "WRONG_TARGET wrong (../../.agents/skills/ok)"
  check "BROKEN_LINK dead"
  grep -q " ok\$" <<<"$out" && { echo "FAIL: clean skill 'ok' was reported"; fail=1; }

  # apply --fix, then assert the fixable cases are gone on a re-scan
  scan fix >/dev/null
  local out2; out2=$(scan nofix)
  for code in "NO_SYMLINK nolink" "NOT_SYMLINK realdir" "WRONG_TARGET wrong (../../.agents/skills/ok)"; do
    grep -q "^$code\$" <<<"$out2" && { echo "FAIL: '$code' survived --fix"; fail=1; }
  done
  # verify the structural repairs actually happened
  [ -L "$CLAUDE/nolink" ] || { echo "FAIL: nolink symlink not created"; fail=1; }
  [ -L "$CLAUDE/realdir" ] && [ -d "$AGENTS/realdir" ] || { echo "FAIL: realdir not moved+linked"; fail=1; }
  [ "$(readlink "$CLAUDE/wrong")" = "../../.agents/skills/wrong" ] || { echo "FAIL: wrong not relinked"; fail=1; }
  # dangling link (no body) is removed, not left behind
  [ ! -L "$CLAUDE/dead" ] || { echo "FAIL: dead symlink not removed by --fix"; fail=1; }

  rm -rf "$T"
  [ "$fail" = 0 ] && { echo "self-test OK"; return 0; } || { echo "self-test FAILED"; return 1; }
}

main() {
  case "${1:-}" in
    --self-test) self_test ;;
    --fix)       scan fix ;;
    "") scan nofix ;;
    *) echo "usage: skills-sync.sh [--fix] [--self-test]" >&2; exit 2 ;;
  esac
}
main "$@"
