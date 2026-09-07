#!/usr/bin/env bash
# Runs the statusline's two --selftest modes (#609).
set -euo pipefail
dir=$(cd "$(dirname "$0")" && pwd)
python3 "$dir/table-statusline.py" --selftest
bash "$dir/helpers/usage-segment.sh" --selftest </dev/null
