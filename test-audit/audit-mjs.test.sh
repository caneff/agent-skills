#!/usr/bin/env bash
# Runs the JS port's node:test suite, audit.test.mjs (#609, #1743). audit.mjs
# needs @babel/parser, so install from the tracked lockfile the first time.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
[ -d node_modules ] || npm ci --silent
exec node --test audit.test.mjs
