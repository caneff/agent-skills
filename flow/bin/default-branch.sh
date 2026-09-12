# Sourced, not run: the one default-branch resolver merge-cleanup and
# implement-dispatch share. The installer links it beside them in
# ~/.local/bin, so each sources it from its own directory.

default_of() { # default_of <path> -> main, master, whatever origin points at
  local d
  d=$(git -C "$1" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)
  [ -n "$d" ] && { echo "${d#origin/}"; return; }
  for d in main master; do
    git -C "$1" show-ref -q --verify "refs/remotes/origin/$d" && { echo "$d"; return; }
  done
  echo main
}
