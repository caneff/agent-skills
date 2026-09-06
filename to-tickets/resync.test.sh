#!/usr/bin/env bash
# Diffs the three setup issue-tracker templates against the live adapter doc
# (docs/agents/issue-tracker.md). Fails if the tracker-agnostic triage rules
# drift, or a template is missing the parent/blocked-by/type relationships
# convention, or to-tickets still hardcodes a raw tracker command instead of
# deferring to the adapter doc.
set -euo pipefail
cd "$(dirname "$0")/.."

LIVE=docs/agents/issue-tracker.md
TEMPLATES=(
  setup-matt-pocock-skills/issue-tracker-github.md
  setup-matt-pocock-skills/issue-tracker-gitlab.md
  setup-matt-pocock-skills/issue-tracker-local.md
)

section() { # section <file> <heading>
  awk -v h="$2" '
    $0 == h {p=1; next}
    p && /^## / {exit}
    p {print}
  ' "$1"
}

fail=0
live_gate=$(section "$LIVE" "## Grilling gate on new tickets")

for t in "${TEMPLATES[@]}"; do
  gate=$(section "$t" "## Grilling gate on new tickets")
  if [ -z "$gate" ]; then
    echo "FAIL: $t has no Grilling gate section"
    fail=1
  elif [ "$gate" != "$live_gate" ]; then
    echo "FAIL: $t Grilling gate section drifted from $LIVE"
    diff <(echo "$live_gate") <(echo "$gate") || true
    fail=1
  fi

  if ! grep -q "Relationships (parent" "$t"; then
    echo "FAIL: $t missing the parent/blocked-by/type relationships convention"
    fail=1
  fi
done

if grep -q "sub_issues" to-tickets/SKILL.md; then
  echo "FAIL: to-tickets/SKILL.md still has a raw sub_issues gh api call"
  fail=1
fi

[ "$fail" -eq 0 ] && echo "ok - templates match the live adapter doc"
exit "$fail"
