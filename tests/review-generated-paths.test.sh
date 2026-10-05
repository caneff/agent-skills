#!/usr/bin/env bash
# This repo's docs/agents/review-generated-paths.txt (#1437): present, and every
# pathspec in it matches a tracked file. The capture in
# multi-axis-code-review/SKILL.md excludes a pathspec that matches nothing
# without complaint, so a typo or a deleted lockfile would leave the declaration
# excluding nothing while the file looks fine.
set -u
root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1
f=docs/agents/review-generated-paths.txt
[ -f "$f" ] || { echo "FAIL: $f is missing"; exit 1; }
n=0; fail=0
while IFS= read -r p || [ -n "$p" ]; do
  p=${p%$'\r'}
  case "$p" in ''|'#'*) continue ;; esac
  n=$((n + 1))
  [ -n "$(git ls-files -- "$p" | head -1)" ] || { echo "FAIL: '$p' matches no tracked file"; fail=1; }
done <"$f"
[ "$n" -gt 0 ] || { echo "FAIL: $f declares no path"; exit 1; }
[ "$fail" -eq 0 ] && echo "ok: $n declared pathspecs each match a tracked file"
exit "$fail"
