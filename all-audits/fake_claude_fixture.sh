#!/usr/bin/env bash
# Test fixture (#559): a fake `claude` binary for driver_test.py's manifest
# tests. Reads the last argv (the audit prompt), and — only for the audit
# named "dead-code" — writes a report + the manifest the prompt asked for.
# Any other audit (e.g. "duplication" in the same test run) writes nothing,
# simulating a crashed/silent process so the driver must render a missing
# manifest as a named failure, never as a silent skip.
set -euo pipefail
prompt="${*: -1}"

manifest="$(printf '%s' "$prompt" | grep -oP 'write a manifest to \K\S+' || true)"
[ -n "$manifest" ] || exit 0

case "$prompt" in
  /dead-code\ *)
    dir="$(dirname "$manifest")/report"
    mkdir -p "$dir"
    echo '<html><body>dead-code report</body></html>' >"$dir/report.html"
    mkdir -p "$(dirname "$manifest")"
    printf '{"report_path": "%s/report.html", "count": 1, "headline": "one finding"}\n' "$dir" >"$manifest"
    ;;
  *) : ;;  # every other audit: write nothing — the missing-manifest case
esac
