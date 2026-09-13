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

# A body Claude Code loads from the skills dir: a skill (SKILL.md) or a
# function-hook plugin (.claude-plugin/plugin.json) (#740).
is_body() { [ -d "$1" ] && { [ -f "$1/SKILL.md" ] || [ -f "$1/.claude-plugin/plugin.json" ]; }; }

scan() {
  local fix="$1" d n want tgt
  # claude/ entries: the load-bearing pattern. Must be a symlink -> ../../.agents/skills/<n>
  for d in "$CLAUDE"/*; do
    n=$(basename "$d"); want="../../.agents/skills/$n"
    if [ -L "$d" ]; then
      if ! is_body "$d"; then
        if [ -d "$AGENTS/$n" ]; then
          # target exists but isn't a body (no marker, or a dangling
          # plugin.json symlink) — relinking to it never converges (#741)
          echo "NOT_A_BODY $n"
        else
          echo "BROKEN_LINK $n"
          if [ "$fix" = fix ]; then
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
    elif is_body "$d"; then
      echo "NOT_SYMLINK $n"
      if [ "$fix" = fix ]; then
        # Refuse if a canonical body already exists — moving would clobber it
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
    is_body "$d" || continue; n=$(basename "$d")
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
  mkplug() { mkdir -p "$1/.claude-plugin"; echo '{}' > "$1/.claude-plugin/plugin.json"; }

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
  # clean: a function-hook plugin body (plugin.json, no SKILL.md) + correct
  # symlink; Claude Code loads these from the skills dir (#740)
  mkplug "$AGENTS/hookplug"; ln -s "../../.agents/skills/hookplug" "$CLAUDE/hookplug"
  # NO_SYMLINK for a plugin body too
  mkplug "$AGENTS/hooknolink"
  # NOT_A_BODY: claude link resolves to a directory with no marker file (#741)
  mkdir -p "$AGENTS/nomarker"; ln -s "../../.agents/skills/nomarker" "$CLAUDE/nomarker"
  # NOT_A_BODY: claude link resolves to a directory whose plugin.json is a
  # dangling symlink (#741)
  mkdir -p "$AGENTS/danglejson/.claude-plugin"
  ln -s "/no/such/target" "$AGENTS/danglejson/.claude-plugin/plugin.json"
  ln -s "../../.agents/skills/danglejson" "$CLAUDE/danglejson"

  local out; out=$(scan nofix)
  local fail=0
  check() { grep -q "^$1\$" <<<"$out" || { echo "FAIL: expected '$1'"; fail=1; }; }
  check "NO_SYMLINK nolink"
  check "NOT_SYMLINK realdir"
  check "WRONG_TARGET wrong (../../.agents/skills/ok)"
  check "BROKEN_LINK dead"
  grep -q " ok\$" <<<"$out" && { echo "FAIL: clean skill 'ok' was reported"; fail=1; }
  grep -q " hookplug\$" <<<"$out" && { echo "FAIL: clean plugin 'hookplug' was reported"; fail=1; }
  check "NO_SYMLINK hooknolink"
  check "NOT_A_BODY nomarker"
  check "NOT_A_BODY danglejson"

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
  grep -q " hookplug\$" <<<"$out2" && { echo "FAIL: plugin 'hookplug' reported after --fix"; fail=1; }
  [ -L "$CLAUDE/hooknolink" ] || { echo "FAIL: hooknolink symlink not created"; fail=1; }
  # --fix must never converge on a non-body by relinking to itself (#741)
  for code in "NOT_A_BODY nomarker" "NOT_A_BODY danglejson"; do
    grep -q "^$code\$" <<<"$out2" || { echo "FAIL: '$code' missing after --fix"; fail=1; }
  done
  [ -L "$CLAUDE/nomarker" ] || { echo "FAIL: nomarker link removed by --fix"; fail=1; }
  [ -L "$CLAUDE/danglejson" ] || { echo "FAIL: danglejson link removed by --fix"; fail=1; }

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
