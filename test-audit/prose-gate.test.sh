#!/usr/bin/env bash
# The prose-assertion gate as this repo's own merge gate (#1959). A test whose
# only assertions are containment checks on a prose file fails the seam,
# naming the file and the test; a detector that crashes or reads no test file
# fails it too (exit 2), never "no findings".
#
# all.sh: repo-wide (scans every tracked test file, so no directory edge can pin it)
# Discovered by tests/all.sh's `*.test.sh` rule, so wiring is this file alone.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
root=$(git rev-parse --show-toplevel)

python3 audit.py --prose-gate "$root"
