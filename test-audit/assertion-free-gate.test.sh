#!/usr/bin/env bash
# The assertion-free check as this repo's own merge gate (#645). Both parsers
# run over the whole tree in --gate mode: smell 1 only, fixtures excluded,
# non-zero exit on any hit. The other four smells stay report-only -- see
# GATE_SMELL in audit.py for why.
#
# Discovered by tests/all.sh's `*.test.sh` rule, so wiring is this file alone.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
root=$(git rev-parse --show-toplevel)

python3 audit.py --gate "$root"

# audit.mjs needs @babel/parser, same tracked-lockfile bootstrap as
# audit-mjs.test.sh; it exits 2 with a `npm ci` message if that is missing.
[ -d node_modules ] || npm ci --silent
node audit.mjs --gate "$root"
