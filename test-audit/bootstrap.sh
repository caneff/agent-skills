#!/usr/bin/env bash
# Installs test-audit's node dependencies from the tracked lockfile, once.
# Called by the four suites that need them, which tests/all.sh runs at the
# same time (#1845): `[ -d node_modules ]` let a caller run against the
# directory a sibling's `npm ci` had just created. The check here is "npm
# finished" (its hidden lockfile, written last) plus the package itself, and a
# lock makes every other caller wait for the install in progress.
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
installed() { [ -f node_modules/.package-lock.json ] && [ -f node_modules/@babel/parser/package.json ]; }
installed && exit 0
(
  flock 9
  installed || npm ci --silent
) 9<.   # the lock is on the directory itself: no lock file to leave untracked
installed || { echo "bootstrap.sh: npm ci left test-audit/node_modules without @babel/parser" >&2; exit 2; }
