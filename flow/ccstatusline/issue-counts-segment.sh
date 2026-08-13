#!/usr/bin/env bash
# ccstatusline second-line widget: compact wayfinder/issue counts for the
# session's repo. Reads the Claude session JSON on stdin (cwd), prints the
# cached line instantly, and refreshes in the background when older than TTL.
# Never calls gh inline, so it always returns well under the render timeout.
TTL=60

cwd=$(jq -r '.workspace.current_dir // .cwd // empty' 2>/dev/null)
[ -z "$cwd" ] && exit 0
git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1 || exit 0   # only in a repo

cache_dir="$HOME/.cache/issue-counts"; mkdir -p "$cache_dir"
cache="$cache_dir/$(printf '%s' "$cwd" | sha1sum | cut -c1-16)"

[ -f "$cache" ] && cat "$cache"                                # show what we have

if [ ! -f "$cache" ] || [ "$(( $(date +%s) - $(stat -c %Y "$cache") ))" -ge "$TTL" ]; then
  ( cd "$cwd" && issue-counts --status > "$cache.tmp.$$" 2>/dev/null \
      && mv "$cache.tmp.$$" "$cache" || rm -f "$cache.tmp.$$" ) >/dev/null 2>&1 &
  disown
fi
