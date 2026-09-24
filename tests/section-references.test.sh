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
run_fixture step-forms-valid
run_fixture step-sentence-valid
run_fixture step-colon-name-valid
run_fixture mention-escaped-valid
run_fixture code-span-name-valid
run_fixture step-prefix-exact-valid
run_fixture double-backtick-name-valid
run_fixture step-locator-inline-code-valid
run_fixture multiline-code-span-valid

for fixture in pointer-suffix-invalid bare-cross-file-collision step-heading-name-invalid \
  step-number-invalid step-range-invalid \
  step-colon-invalid step-descending-invalid step-emdash-invalid step-fence-steps-invalid \
  step-fence-nested-invalid step-fence-char-invalid step-fence-length-invalid \
  step-fence-info-invalid step-colon-name-invalid mention-unescaped-invalid long-name-step-invalid inline-code-name-invalid \
  step-prefix-collision-invalid possessive-inline-code-invalid conjunction-inline-code-invalid \
  step-duplicate-exact-invalid step-prefix-ambiguous-invalid multiline-code-span-unterminated-invalid; do
  if run_fixture "$fixture"; then
    echo "FAIL: checker accepted fixture $fixture"
    exit 1
  fi
done

# A backtick before a list item, heading, fence or table row must not pair
# with one after it, and one before a "|" line that is not a table row must;
# otherwise the pointer reads as inside a code span and skips the inline-code
# guard. Each must fail on that guard, not another.
for fixture in code-span-list-boundary-invalid code-span-heading-boundary-invalid \
  code-span-fence-boundary-invalid code-span-table-boundary-invalid \
  code-span-ordered-list-boundary-invalid code-span-pipe-continuation-invalid; do
  if output=$(run_fixture "$fixture" 2>&1); then
    echo "FAIL: checker accepted fixture $fixture"
    exit 1
  fi
  if ! grep -q "is cut at inline code" <<<"$output"; then
    echo "FAIL: fixture $fixture failed for another reason: $output"
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
