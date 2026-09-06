#!/usr/bin/env bash
# No audit skill doc restates AUDIT-RUN.md's write-and-deliver sentence
# (#557) — each points at it instead. Grep every SKILL.md except
# AUDIT-RUN.md's own harness home for the telltale restated phrase.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

hits="$(grep -rl 'Resolve `<tmpdir>` from `\$TMPDIR`, fall back to `/tmp`\. Write both to' \
  --include=SKILL.md "$ROOT" 2>/dev/null || true)"

[ -z "$hits" ] || fail "restates the write-and-deliver sentence instead of pointing at AUDIT-RUN.md: $hits"

echo "ok"
