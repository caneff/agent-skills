#!/usr/bin/env bash
# Behavioral test for the run-audits.sh index/--only/--out seam (#376): the
# --index path must rebuild the index over whatever reports already sit in an
# --out dir, WITHOUT running any audit or needing a full sweep to have run.
#
# No `claude` is invoked here: --index runs no audits, and AUDITS_NO_SYNTH=1
# skips the one synthesis call. So this test is hermetic and offline.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/run-audits.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Prepopulate two audits' reports as if prior `--only` runs had landed them.
for name in dead-code test-audit; do
  mkdir -p "$tmp/collection/$name"
  echo "<html><body>$name report</body></html>" >"$tmp/collection/$name/report.html"
done

# --index over the dir: rebuild the index, run nothing.
AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$tmp" >"$tmp/run.log" 2>&1 \
  || fail "--index run exited non-zero; see: $(cat "$tmp/run.log")"

index="$tmp/collection/index.html"
[ -f "$index" ] || fail "index.html was not built at $index"
grep -q "dead-code" "$index" || fail "index missing dead-code row"
grep -q "test-audit" "$index" || fail "index missing test-audit row"
grep -q 'dead-code/report.html' "$index" || fail "index missing link to dead-code report"

# --index must not have invoked any audit: no per-audit log should exist.
if compgen -G "$tmp/logs/*.log" >/dev/null; then
  fail "--index ran audits (found logs) — it must rebuild over existing reports only"
fi

echo "ok"
