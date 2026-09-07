#!/usr/bin/env bash
# Behavioral test for auditlib's walk exclusion (#555): a fixture tree with a
# vendor/ and node_modules/ dir must yield no files from either. The unit
# selfcheck (auditlib.py --selfcheck) covers a smaller case; this exercises a
# tree matching the ticket's own AC wording via the public CLI surface.
#
# The second fixture (#611) covers `walk_source`'s `skip=` predicate: passing
# `auditlib.is_test_or_fixture` filters out test files, `__init__.py`, and a
# `fixtures/` dir the same way mutation-audit's `_sibling_tests` used to by
# hand.
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

mkdir -p "$tmp/pkg/fixtures"
echo "x = 1" >"$tmp/pkg/widget.py"
echo "x = 1" >"$tmp/pkg/test_widget.py"
echo "x = 1" >"$tmp/pkg/__init__.py"
echo "x = 1" >"$tmp/pkg/fixtures/sample.py"

out2="$(python3 -c "
import sys
sys.path.insert(0, '$HERE')
import auditlib
print('\n'.join(auditlib.walk_source('$tmp/pkg', skip=auditlib.is_test_or_fixture)))
")"

[ "$out2" = "widget.py" ] || fail "expected only widget.py with skip=is_test_or_fixture, got: $out2"

echo "ok"
