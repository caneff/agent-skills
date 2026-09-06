#!/usr/bin/env bash
# Thin wrapper so tests/all.sh's *.test.sh glob picks up the harness
# selfcheck runner (#556).
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/run_selfchecks.py"
