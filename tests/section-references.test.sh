#!/usr/bin/env bash
# Ensures prose section references remain valid when their target headings move.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

bash tests/check-section-references.sh

target=implement/SKILL.md
backup=$(mktemp)
cp "$target" "$backup"
trap 'cp "$backup" "$target"; rm -f "$backup"' EXIT

sed -i 's/^### Build$/### Build renamed for test/' "$target"

if bash tests/check-section-references.sh; then
  echo "FAIL: checker accepted a renamed referenced heading"
  exit 1
fi

echo "ok"
