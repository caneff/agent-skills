#!/usr/bin/env bash
# Guards #1259: on a sweep ticket's PR, every sweep item the worker leaves
# undone is a `leftover` line in the dispositions sidecar under its
# `<file> <id>`, because `runfile.py leftover` harvests the sidecar and
# nothing else; and the pre-report gate refuses a sweep item that is neither.
# Prose assertion over SKILL.md; the mechanism is runfile_test.py's and
# pre-report-gate.test.sh's.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
flatten() { tr '\n' ' ' | tr -s ' '; }
review="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$here/SKILL.md" | flatten)"
[ -n "$review" ] || { echo "FAIL: could not extract § Review" >&2; exit 1; }
before_pr="$(sed -n '/^### Before the PR$/,/^### The PR$/p' "$here/SKILL.md" | flatten)"
[ -n "$before_pr" ] || { echo "FAIL: could not extract § Before the PR" >&2; exit 1; }
fail=0
need() {
  case "$2" in *"$3"*) ;; *) echo "FAIL: $1 is missing: $3" >&2; fail=1 ;; esac
}
need "§ Review" "$review" 'sweep ticket'
need "§ Review" "$review" 'every sweep item not fixed in the PR'
need "§ Review" "$review" '`leftover` line in the dispositions sidecar'
need "§ Review" "$review" '`<file> <id>`'
need "§ Before the PR" "$before_pr" 'sweep item that is neither'
verify="$(sed -n '/^### 6\. The verification pass$/,/^## Why separate axes$/p' "$here/../multi-axis-code-review/SKILL.md" | flatten)"
[ -n "$verify" ] || { echo "FAIL: could not extract multi-axis § 6" >&2; exit 1; }
need "multi-axis § 6" "$verify" 'Keep every line already in the file whose id holds a space'
[ "$fail" = 0 ] && echo "ok: sweep items left undone are sidecar leftovers"
exit "$fail"
