#!/usr/bin/env bash
# The assertion-free and duplicate-name checks as this repo's own merge gate
# (#645, #1488). Both parsers run over the whole tree in --gate mode: those two
# smells only, fixtures excluded, non-zero exit on any hit. Every other smell
# stays report-only -- see SKILL.md § Gate mode for why.
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
