# Sourced, not run: what merge-cleanup and implement-dispatch read from a
# repo's origin. Each follows its own ~/.local/bin link back to flow/bin and
# sources it from there, so the installer does not link it.

default_of() { # default_of <path> -> main, master, whatever origin points at
  local d
  d=$(git -C "$1" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)
  [ -n "$d" ] && { echo "${d#origin/}"; return; }
  for d in main master; do
    git -C "$1" show-ref -q --verify "refs/remotes/origin/$d" && { echo "$d"; return; }
  done
  echo main
}
slug_of() { # slug_of <path> -> owner/name, for the gh calls
  local url; url=$(git -C "$1" remote get-url origin 2>/dev/null) || return 1
  url="${url%.git}"; url="${url#*github.com/}"; url="${url#*github.com:}"
  echo "$url"
}
