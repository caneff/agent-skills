#!/usr/bin/env bash
# Contract test for teach-filing.sh: `gh issue create` answers, once per
# session, with WORKFLOW.md § Before filing a ticket and the open issues whose
# title matches the new ticket's component, from a search the hook runs.
# `gh` is stubbed via PATH so this runs offline.
# Run: bash flow/claude/hooks/teach-filing.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
hook="$here/teach-filing.sh"

# gh stub: records its argv, then answers `issue list` with $STUB_ISSUES, or
# fails with $STUB_ERR when that is set.
mkdir -p "$tmp/bin"
cat > "$tmp/bin/gh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_ARGS"
[ -z "${STUB_ERR:-}" ] || { echo "$STUB_ERR" >&2; exit 1; }
[ "$1 $2" = "issue list" ] && printf '%s' "${STUB_ISSUES:-}"
exit 0
STUB
chmod +x "$tmp/bin/gh"
export STUB_PATH="$tmp/bin" STUB_ARGS="$tmp/gh.args"

section=(" § Before filing a ticket" "(\`gh issue comment <n>\`) instead of a new issue.")

export STUB_ISSUES=$'#1365 merge-cleanup: repo-declared discardable paths\n#1290 merge-cleanup: remove nested worktrees'
got=$(context "$hook" s1 'gh issue create --repo caneff/agent-skills --title "merge-cleanup: refuse a dirty primary" --label ready-for-agent --body "$(cat <<'"'"'EOF2'"'"'
Body that mentions gh issue create.
EOF2
)"')
expect_has "extraction: gh issue create returns § Before filing a ticket" "$got" "${section[@]}"
expect_has "the search's matches are listed" "$got" "#1365 merge-cleanup: repo-declared discardable paths" "#1290"
if grep -qxF -- "--repo" "$STUB_ARGS" && grep -qxF "caneff/agent-skills" "$STUB_ARGS" \
   && grep -qxF "merge-cleanup in:title" "$STUB_ARGS" && grep -qxF "open" "$STUB_ARGS"; then
  echo "PASS: search names the repo, the component and open issues"
else
  echo "FAIL: search args were: $(paste -sd' ' "$STUB_ARGS")"; fails=1
fi
expect_none "second gh issue create in the same session" \
  "$(context "$hook" s1 'gh issue create --title "merge-cleanup: another" --body x')"

# No colon in the title: the first identifier-shaped word is the component.
got=$(context "$hook" s2 "gh issue create -t 'Make merge_cleanup dry-run deterministic' -b x")
expect_has "component from an identifier word" "$got" "${section[@]}"
grep -qxF "merge_cleanup in:title" "$STUB_ARGS" \
  && echo "PASS: identifier word searched" || { echo "FAIL: searched $(paste -sd' ' "$STUB_ARGS")"; fails=1; }

export STUB_ISSUES=""
expect_has "no match is said, with the space searched" \
  "$(context "$hook" s3 'gh issue create --title "teach-lib: x" --body y')" "${section[@]}" "No open issue" "teach-lib"

# A failed search never reads as "no duplicates" (defect class 1).
got=$(STUB_ERR="HTTP 502" context "$hook" s4 'gh issue create --title "teach-lib: x" --body y')
expect_has "failed search is reported as failed" "$got" "${section[@]}" "failed" "HTTP 502"
if [[ "$got" == *"No open issue"* ]]; then echo "FAIL: failed search read as no match"; fails=1; fi

rm -f "$STUB_ARGS"
got=$(context "$hook" s5 "gh issue create --web")
expect_has "no title: says no search ran" "$got" "${section[@]}" "no search ran"
[ -e "$STUB_ARGS" ] && { echo "FAIL: gh ran with no component"; fails=1; } || echo "PASS: gh not run with no component"

expect_none "unrelated command" "$(context "$hook" s6 "gh issue list --label backlog")"
expect_none "trigger in a grep pattern" "$(context "$hook" s6 "rg 'gh issue create' file-ticket/")"
expect_none "trigger in a heredoc body" "$(context "$hook" s6 "cat > f.md <<'EOF2'
gh issue create --title x
EOF2")"

copy_tree
sed -i 's/^## Before filing a ticket$/## Filing/' "$tmp/tree/claude/WORKFLOW.md"
got=$(context "$tmp/tree/claude/hooks/teach-filing.sh" s7 'gh issue create --title "a: b" --body c')
expect_has "renamed heading is reported, not silent" "$got" "Before filing a ticket" "not found"

finish
