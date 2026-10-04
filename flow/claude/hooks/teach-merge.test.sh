#!/usr/bin/env bash
# Contract test for teach-merge.sh: `gh pr view` or `gh pr checks`, the reads
# that come before a merge, answer with OPERATIONS.md § Merge preconditions
# once per session.
# Run: bash flow/claude/hooks/teach-merge.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
hook="$here/teach-merge.sh"

section=(" § Merge preconditions" "with \`--repo owner/name\`, and runs only after \`gh pr view\` shows the PR")

got=$(context "$hook" s1 "gh pr view 1412 --repo caneff/agent-skills --json isDraft,mergeStateStatus")
expect_has "extraction: gh pr view returns § Merge preconditions" "$got" "${section[@]}"
expect_none "gh pr checks in the same session" "$(context "$hook" s1 "gh pr checks 1412")"
expect_has "extraction: gh pr checks in a new session" "$(context "$hook" s2 "gh pr checks 1412 --watch")" "${section[@]}"

expect_none "unrelated gh command" "$(context "$hook" s3 "gh pr list --state open")"
expect_none "gh issue view is not gh pr view" "$(context "$hook" s3 "gh issue view 12")"
expect_none "trigger in a grep pattern" "$(context "$hook" s3 "grep -rn 'x; gh pr view' implement/")"
expect_none "trigger in a heredoc body" "$(context "$hook" s3 "cat > notes.md <<'EOF2'
gh pr view 12
EOF2")"

copy_tree
sed -i 's/^## Merge preconditions$/## Merging/' "$tmp/tree/claude/OPERATIONS.md"
got=$(context "$tmp/tree/claude/hooks/teach-merge.sh" s4 "gh pr view 12")
expect_has "renamed heading is reported, not silent" "$got" "Merge preconditions" "not found"

finish
