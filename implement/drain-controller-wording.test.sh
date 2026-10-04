#!/usr/bin/env bash
# Guards #1415: `drain` names the controller `drain` in every brief and no
# session bears that name, so implement/SKILL.md § Control must say what a worker
# does then (a worker that tried to resolve and send would stop idle at its
# first job notice, with no PR). Prose assertion over § Control.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
control="$(sed -n '/^## Control$/,/^## Light tier$/p' "$here/SKILL.md" | tr '\n' ' ' | tr -s ' ')"
[ -n "$control" ] || { echo "FAIL: could not extract § Control" >&2; exit 1; }
fail=0
check_in() { case "$control" in *"$1"*) ;; *) echo "FAIL: § Control is missing: $1" >&2; fail=1 ;; esac; }
check_in 'A controller named `drain` is no session'
check_in 'Resolve nothing and send nothing: no question, no job notice'
check_in 'you go idle, and `drain` waits for exactly that'
grep -q 'CONTROLLER = "drain"' "$here/../drain/drain.py" \
  || { echo "FAIL: drain.py no longer names the controller \`drain\`" >&2; fail=1; }
[ "$fail" = 0 ] || exit 1
echo "PASS implement/drain-controller-wording.test.sh"
