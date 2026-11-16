# Sourced, never run: the capture functions of multi-axis-code-review/SKILL.md § 4.
# They live here, not in SKILL.md, because of #1693; the reason is stated in
# tests/skill-md-no-positional.test.sh.
#
# The caller's shell has set `dir`, `n`, `worktree`, `generated` and `excludes`
# (SKILL.md's preamble) before it sources this file.

capture_stat() { # <range>: the one stat line every axis prompt carries
  local gen="" count=0 list=""
  if [ "${#generated[@]}" -gt 0 ]; then
    gen=$(git -C "$worktree" diff --name-only "$1" -- "${generated[@]}") || return 1
    [ -z "$gen" ] || { count=$(printf '%s\n' "$gen" | wc -l); list=": $(printf '%s\n' "$gen" | paste -sd, -)"; }
  fi
  printf 'captured: %s; excluded %s generated file(s)%s\n' \
    "$(git -C "$worktree" diff --shortstat "$1" -- . "${excludes[@]}")" "$count" "$list"
}

# The publish protocol, stated once for both capture modes. Each mode sets its
# own `patch` stem, takes a temp path from new_capture, writes into it, then
# hands both to publish_capture, which appends the temp path's random suffix.
new_capture() { mktemp "$dir/.diff-$n.XXXXXX"; }   # unique per invocation; prints the path
publish_capture() { # <tmp> <stem>: fail on an empty write here, not inside three sub-agents
  [ -s "$1" ] || { rm -f "$1"; echo "capture for $2 is empty" >&2; return 1; }
  # The suffix is mktemp's, unique per invocation; a shell pid is only per shell,
  # and two captures at one revision in one shell would share it.
  mv "$1" "$2-${1##*.}.patch" &&        # atomic publish: no axis ever reads a half-written patch
    wc -l "$2-${1##*.}.patch"           # this exact path and this count go in every prompt
}
