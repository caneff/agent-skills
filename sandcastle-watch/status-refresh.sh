#!/usr/bin/env bash
# Folded into sandcastle-watch.sh as the `refresh` verb (issue #108). Kept as a
# thin shim so any existing caller keeps working: status-refresh.sh <log> <root> [once].
exec "$(dirname -- "${BASH_SOURCE[0]}")/sandcastle-watch.sh" refresh "$@"
