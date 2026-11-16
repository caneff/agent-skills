#!/usr/bin/env bash
# The assertion-free and duplicate-name checks as this repo's own merge gate.
# Both parsers run over the whole tree in --gate mode: those two
# smells only, fixtures excluded, non-zero exit on any hit. Every other smell
# stays report-only -- see SKILL.md § Gate mode for why.
#
# all.sh: repo-wide (scans every tracked file, so no directory edge can pin it)
# Discovered by tests/all.sh's `*.test.sh` rule, so wiring is this file alone.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
root=$(git rev-parse --show-toplevel)

python3 audit.py --gate "$root"

# audit.mjs needs @babel/parser, installed by bootstrap.sh from the tracked
# lockfile; audit.mjs exits 2 with a `npm ci` message if it is still missing.
bash ./bootstrap.sh
node audit.mjs --gate "$root"
