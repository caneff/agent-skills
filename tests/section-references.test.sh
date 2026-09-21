#!/usr/bin/env bash
# Ensures prose section references remain valid when their target headings move.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

bash tests/check-section-references.sh

run_fixture() {
  local name fixture
  name=$1
  fixture=$(mktemp -d)
  cp -R "tests/fixtures/section-references/$name/." "$fixture"
  git -C "$fixture" init -q
  git -C "$fixture" add -A
  SECTION_REFERENCES_ROOT="$fixture" bash tests/check-section-references.sh
}

run_fixture text-suffix-valid
run_fixture heading-trailing-punctuation-valid
run_fixture step-locator-valid
run_fixture step-variants-valid
run_fixture step-heading-prose-valid

for fixture in pointer-suffix-invalid bare-cross-file-collision step-heading-name-invalid \
  step-number-invalid step-range-invalid; do
  if run_fixture "$fixture"; then
    echo "FAIL: checker accepted fixture $fixture"
    exit 1
  fi
done

target=implement/SKILL.md
backup=$(mktemp)
cp "$target" "$backup"
trap 'cp "$backup" "$target"; rm -f "$backup"' EXIT

sed -i 's/^### Build$/### Compile for test/' "$target"

if bash tests/check-section-references.sh; then
  echo "FAIL: checker accepted a renamed referenced heading"
  exit 1
fi

echo "ok"
