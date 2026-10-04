#!/usr/bin/env bash
# Fixture for the `prose-assertion` category (answer-key row 13): the only
# assertion is that a Markdown file contains a sentence. It passes, because
# tests/all.sh discovers every tracked `*.test.sh`, fixtures included.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
grep -q 'Answer key' "$here/answer-key.md" || { echo "FAIL: sentence missing" >&2; exit 1; }
