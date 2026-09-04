#!/usr/bin/env bash
# ccstatusline widget: live burndown progress for the session's repo.
# Reads the Claude session JSON on stdin and renders the repo's burndown
# progress file, or nothing when no burn is live. Pass a file path as $1 to
# render that file directly (the self-check below uses this).
#
# Line grammar for the progress file (the single documented home — burndown/SKILL.md
# points here instead of restating it):
#   burning #<n>          claimed, build in flight
#   #<n> pr <ref>         PR open, awaiting a human merge
#   #<n> landed <sha>     ticket landed on main
#   #<n> parked: <why>    ticket handed to a human
#   done                  the loop stopped
# A burn builds several tickets at once, so several `burning` lines are open
# at the same time. A ticket's state is its last line: later lines supersede
# earlier ones, so `pr` then `landed` is one ticket that ended up merged.
# Where a human owns the merge, `pr` is where a ticket stops.
render() {
  local f=$1
  [ -f "$f" ] || return 0
  # a file untouched for 12h is an abandoned burn, not a live one
  [ -n "$(find "$f" -mmin -720 2>/dev/null)" ] || return 0
  [ "$(tail -n 1 "$f")" = done ] && return 0
  awk '
    $1 == "burning"  { st[$2] = "build";  next }
    $2 == "pr"       { st[$1] = "pr";     next }
    $2 == "landed"   { st[$1] = "landed"; next }
    $2 == "parked:"  { st[$1] = "parked"; next }
    END {
      for (k in st) n[st[k]]++
      out = "🔥 "
      if (n["build"]) out = out n["build"] "🔨 · "
      if (n["pr"])    out = out n["pr"] "⏳ · "
      out = out n["landed"] + 0 "✓"
      if (n["parked"]) out = out " " n["parked"] "⚠"
      printf "%s", out
    }
  ' "$f"
}

if [ "$1" = --self-check ]; then
  fail=0
  check() { # check <name> <expected> <progress file body>
    local got
    printf '%s\n' "$3" > "$tmp"
    got=$(render "$tmp")
    [ "$got" = "$2" ] && return 0
    printf 'FAIL %s\n  want: %s\n  got:  %s\n' "$1" "$2" "$got" >&2
    fail=1
  }
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT
  check "nothing in flight" '🔥 1✓' 'burning #1
#1 landed abc1234'
  check "several in flight" '🔥 3🔨 · 0✓' 'burning #1
burning #2
burning #3'
  check "one landed, one still building" '🔥 1🔨 · 1✓' 'burning #1
burning #2
#1 landed abc1234'
  check "a park counts once, not as in flight" '🔥 1✓ 1⚠' 'burning #1
#1 parked: needs a human
burning #2
#2 landed abc1234'
  check "a pr awaits a human" '🔥 1⏳ · 0✓' 'burning #1
#1 pr 331'
  check "pr then landed counts once" '🔥 1✓' 'burning #1
#1 pr 331
#1 landed abc1234'
  check "one building, one at pr, one landed" '🔥 1🔨 · 1⏳ · 1✓' 'burning #1
burning #2
burning #3
#2 pr 331
#3 landed abc1234'
  check "prose is not a state change" '🔥 1🔨 · 0✓' 'burning #1
#1 review CANNOT GET CLEAN, 6 findings'
  check "done renders nothing" '' 'burning #1
#1 landed abc1234
done'
  [ "$fail" = 0 ] && echo "burndown-segment: all checks pass"
  exit "$fail"
fi

if [ -n "$1" ]; then
  render "$1"
  exit 0
fi
cwd=$(jq -r '.workspace.current_dir // .cwd // empty' 2>/dev/null)
[ -z "$cwd" ] && exit 0
common=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
[ -z "$common" ] && exit 0
render "$HOME/.cache/burndown/$(basename "$(dirname "$common")").progress"
