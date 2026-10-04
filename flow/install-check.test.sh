#!/usr/bin/env bash
# Contract test for install-check.sh (#1224): a fixture flow dir and a fixture
# HOME, one fault per case. The last case runs the check against this repo's
# own flow/ with a HOME linked the way install.sh links it, so a hook added
# here and never registered fails this suite, not a weekly digest.
# Run: bash flow/install-check.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
check="$here/install-check.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0

# A healthy fixture: flow dir with two hooks (one registered by path under
# ~/.claude/hooks, one run from the repo, one unregistered by design) and a
# HOME linking the settings and the one installed hook.
fixture() { # fixture <name> -> sets FLOW and HOME_DIR
  FLOW="$tmp/$1/flow"; HOME_DIR="$tmp/$1/home"
  mkdir -p "$FLOW/claude/hooks" "$HOME_DIR/.claude/hooks"
  printf 'LINKED_HOOKS=(a.sh a-lib.sh)\nUNREGISTERED_BY_DESIGN=(quiet.sh)\n' > "$FLOW/hooks-manifest.sh"
  for h in a.sh a-lib.sh b.sh quiet.sh a.test.sh; do : > "$FLOW/claude/hooks/$h"; done
  cat > "$FLOW/claude/settings.json" <<JSON
{"hooks":{"PreToolUse":[{"hooks":[
  {"type":"command","command":"/x/.claude/hooks/a.sh"},
  {"type":"command","command":"bash /x/flow/claude/hooks/b.sh","timeout":5}]}]}}
JSON
  ln -s "$FLOW/claude/settings.json" "$HOME_DIR/.claude/settings.json"
  ln -s "$FLOW/claude/hooks/a.sh" "$HOME_DIR/.claude/hooks/a.sh"
  ln -s "$FLOW/claude/hooks/a-lib.sh" "$HOME_DIR/.claude/hooks/a-lib.sh"
}
# case <name> <want-exit> <stderr-needle> -- runs the check on the current fixture
case_() {
  local name=$1 want=$2 needle=$3 out rc
  out=$(bash "$check" --home "$HOME_DIR" --flow "$FLOW" 2>&1); rc=$?
  if [ "$rc" != "$want" ]; then echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return; fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then echo "FAIL: $name — output missing '$needle'"; echo "  out: $out"; fails=1; return; fi
  echo "PASS: $name"
}

fixture ok;            case_ "healthy install passes" 0 ""
fixture plain-settings
rm "$HOME_DIR/.claude/settings.json"; cp "$FLOW/claude/settings.json" "$HOME_DIR/.claude/settings.json"
case_ "settings.json as a plain file fails loudly" 1 "settings.json is a regular file"
fixture wrong-link
rm "$HOME_DIR/.claude/settings.json"; : > "$tmp/other.json"; ln -s "$tmp/other.json" "$HOME_DIR/.claude/settings.json"
case_ "settings.json linked elsewhere fails" 1 "settings.json"
fixture missing-hook
rm "$HOME_DIR/.claude/hooks/a.sh"
case_ "an installed hook that was never linked fails" 1 "a.sh is not linked"
fixture missing-lib
rm "$HOME_DIR/.claude/hooks/a-lib.sh"
case_ "a missing lib fails" 1 "a-lib.sh is not linked"
fixture stale-link
rm "$HOME_DIR/.claude/hooks/a.sh"; ln -s "$tmp/gone" "$HOME_DIR/.claude/hooks/a.sh"
case_ "a link pointing elsewhere fails" 1 "a.sh"
fixture unregistered
: > "$FLOW/claude/hooks/c.sh"
case_ "a repo hook with no settings entry fails" 1 "c.sh is not registered"
fixture registered-unlinked
cat > "$FLOW/claude/settings.json" <<'JSON'
{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"/x/.claude/hooks/b.sh"},{"type":"command","command":"/x/.claude/hooks/a.sh"}]}]}}
JSON
case_ "a hook registered under ~/.claude/hooks but not in the manifest fails" 1 "b.sh is registered under"

fixture misplaced-automode
cat > "$FLOW/claude/settings.json" <<'JSON'
{"permissions":{"autoMode":{"allow":["$defaults"]}},"hooks":{"PreToolUse":[{"hooks":[
  {"type":"command","command":"/x/.claude/hooks/a.sh"},
  {"type":"command","command":"bash /x/flow/claude/hooks/b.sh"}]}]}}
JSON
case_ "a misplaced autoMode block fails the install check" 1 "permissions.autoMode"

# This repo's own flow/, HOME linked from its manifest.
real_home="$tmp/real-home"; mkdir -p "$real_home/.claude/hooks"
# shellcheck source=hooks-manifest.sh
. "$here/hooks-manifest.sh"
ln -s "$here/claude/settings.json" "$real_home/.claude/settings.json"
for h in "${LINKED_HOOKS[@]}"; do ln -s "$here/claude/hooks/$h" "$real_home/.claude/hooks/$h"; done
out=$(bash "$check" --home "$real_home" --flow "$here" 2>&1); rc=$?
if [ "$rc" = 0 ]; then echo "PASS: this repo's hooks are all registered or unregistered by design"
else echo "FAIL: this repo's flow/ — $out"; fails=1; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
