#!/usr/bin/env bash
# Folded into sandcastle-watch.sh as the `segment` verb. ccstatusline's
# commandPath points here and pipes the session JSON on stdin, so this stays a
# passthrough shim — the freshness window (TTL) now lives once, in sandcastle-watch.sh.
exec "$(dirname -- "${BASH_SOURCE[0]}")/sandcastle-watch.sh" segment
