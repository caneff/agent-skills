#!/usr/bin/env bash
# Runs upstream.py's offline selfcheck (lock parsing, extras merge, the
# root-tree quirk, the per-repo cache) so tests/all.sh's *.test.sh glob picks
# it up. No network.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/upstream.py" --selfcheck
