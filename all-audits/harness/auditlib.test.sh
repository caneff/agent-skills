#!/usr/bin/env bash
# Behavioral test for auditlib's walk exclusion (#555): a fixture tree with a
# vendor/ and node_modules/ dir must yield no files from either. The unit
# selfcheck (auditlib.py --selfcheck) covers a smaller case; this exercises a
# tree matching the ticket's own AC wording via the public CLI surface.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/vendor" "$tmp/node_modules/pkg" "$tmp/src"
echo "x = 1" >"$tmp/vendor/lib.py"
echo "x = 1" >"$tmp/node_modules/pkg/lib.py"
echo "x = 1" >"$tmp/src/keep.py"

out="$(python3 -c "
import sys
sys.path.insert(0, '$HERE')
import auditlib
print('\n'.join(auditlib.walk_source('$tmp')))
")"

[ "$out" = "src/keep.py" ] || fail "expected only src/keep.py, got: $out"

echo "ok"
