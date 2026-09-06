#!/usr/bin/env bash
# Thin wrapper so tests/all.sh's *.test.sh glob picks up driver_test.py (#558).
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/driver_test.py"
