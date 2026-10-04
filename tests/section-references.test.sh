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
run_fixture code-span-table-mismatch-valid

# Each invalid fixture is rejected for its own reason: a fixture that fails on
# a crash or a setup error would otherwise count as "rejected". Pairs of
# `fixture|message the checker prints for it`.
for pair in \
  'pointer-suffix-invalid|§ Build typo not found in target.md' \
  'bare-cross-file-collision|bare § Build follows target.md' \
  'step-heading-name-invalid|§ Step 3 not found in target.md' \
  'step-number-invalid|§ Build steps [3] not all numbered items in target.md' \
  'step-range-invalid|§ Build steps [2, 3, 4] not all numbered items in target.md' \
  'step-colon-invalid|§ Build steps [9] not all numbered items in target.md' \
  'step-descending-invalid|§ Build steps [5, 3] run backwards' \
  'step-emdash-invalid|§ Build steps [2, 3, 4] not all numbered items in target.md' \
  'step-fence-steps-invalid|§ Build steps [1] not all numbered items in target.md' \
  'step-fence-nested-invalid|§ Build steps [1] not all numbered items in target.md' \
  'step-fence-char-invalid|§ Build steps [1] not all numbered items in target.md' \
  'step-fence-length-invalid|§ Build steps [1] not all numbered items in target.md' \
  'step-fence-info-invalid|§ Build steps [1] not all numbered items in target.md' \
  'step-colon-name-invalid|§ Build: deployment steps [3] not all numbered items in target.md' \
  'mention-unescaped-invalid|says in words that silence is not zero not found in source.md' \
  'long-name-step-invalid|steps [2] not all numbered items in source.md' \
  'inline-code-name-invalid|§ Build is cut at inline code' \
  'step-prefix-collision-invalid|§ Merge steps [6] not all numbered items in target.md' \
  'possessive-inline-code-invalid|§ Build'"'"'s is cut at inline code' \
  'conjunction-inline-code-invalid|§ Build and is cut at inline code' \
  'step-duplicate-exact-invalid|§ Merge is ambiguous in target.md: matches Merge, Merge' \
  'step-prefix-ambiguous-invalid|§ Mer is ambiguous in target.md: matches Merge, Mermaid' \
  'multiline-code-span-unterminated-invalid|§ Build is cut at inline code'; do
  fixture=${pair%%|*}
  want=${pair#*|}
  if output=$(run_fixture "$fixture" 2>&1); then
    echo "FAIL: checker accepted fixture $fixture"
    exit 1
  fi
  if ! grep -qF -- "$want" <<<"$output"; then
    echo "FAIL: fixture $fixture failed for another reason: $output"
    exit 1
  fi
done

# A backtick before a list item, heading, fence or table row must not pair
# with one after it, and one before a "|" line that is not a table row must;
# otherwise the pointer reads as inside a code span and skips the inline-code
# guard. Each must fail on that guard, not another.
for fixture in code-span-list-boundary-invalid code-span-heading-boundary-invalid \
  code-span-fence-boundary-invalid code-span-table-boundary-invalid \
  code-span-ordered-list-boundary-invalid code-span-pipe-continuation-invalid \
  code-span-list-paragraph-boundary-invalid; do
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
