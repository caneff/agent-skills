#!/usr/bin/env bash
# Contract test for teach-filing.sh: `gh issue create` answers with the open
# issues whose title matches the new ticket's component, from a search the
# hook runs on every filing, and, once per session, with WORKFLOW.md § Before
# filing a ticket.
# `gh` is stubbed via PATH so this runs offline.
# Run: bash flow/claude/hooks/teach-filing.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
hook="$here/teach-filing.sh"

# gh stub: records its argv, sleeps $STUB_SLEEP seconds when set, then answers
# `issue list` with $STUB_ISSUES, or fails with $STUB_ERR when that is set.
mkdir -p "$tmp/bin"
cat > "$tmp/bin/gh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_ARGS"
[ -z "${STUB_SLEEP:-}" ] || sleep "$STUB_SLEEP"
[ -z "${STUB_WARN:-}" ] || echo "$STUB_WARN" >&2
[ -z "${STUB_FAIL_QUIET:-}" ] || exit 4
[ -z "${STUB_ERR:-}" ] || { echo "$STUB_ERR" >&2; exit 1; }
[ "$1 $2" = "issue list" ] && printf '%s' "${STUB_ISSUES:-}"
exit 0
STUB
chmod +x "$tmp/bin/gh"
export STUB_PATH="$tmp/bin" STUB_ARGS="$tmp/gh.args"
# expect_no_gh <name>: gh was never called since STUB_ARGS was last removed.
expect_no_gh() {
  if [ -e "$STUB_ARGS" ]; then echo "FAIL: $1 — gh ran: $(paste -sd' ' "$STUB_ARGS")"; fails=1
  else echo "PASS: $1"; fi
}

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
# The section is shown once per session; the search runs on every filing,
# since its matches belong to the ticket being filed (#1409 story 6, and its
# "the hook runs the open-issue search for the same component and returns the
# matches").
got=$(context "$hook" s1 'gh issue create --repo caneff/agent-skills --title "merge-cleanup: another" --body x')
expect_has "second filing in the session still lists the matches" "$got" "#1365 merge-cleanup: repo-declared discardable paths"
expect_lacks "second filing does not repeat the section" "$got" "${section[0]}"
got=$(STUB_ERR="HTTP 502" context "$hook" s1 'gh issue create --repo caneff/agent-skills --title "merge-cleanup: third" --body x')
expect_has "failed search on a later filing is reported as failed" "$got" "failed" "HTTP 502"

# No colon in the title: the first identifier-shaped word is the component.
got=$(context "$hook" s2 "gh issue create -R caneff/agent-skills -t 'Make merge_cleanup dry-run deterministic' -b x")
expect_has "extraction: component from an identifier word" "$got" "${section[@]}"
grep -qxF "merge_cleanup in:title" "$STUB_ARGS" \
  && echo "PASS: identifier word searched" || { echo "FAIL: searched $(paste -sd' ' "$STUB_ARGS")"; fails=1; }

export STUB_ISSUES=""
expect_has "extraction: no match is said, with the space searched" \
  "$(context "$hook" s3 'gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y')" "${section[@]}" "No open issue" "teach-lib"

# A failed search never reads as "no duplicates" (defect class 1).
got=$(STUB_ERR="HTTP 502" context "$hook" s4 'gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y')
expect_has "extraction: failed search is reported as failed" "$got" "${section[@]}" "failed" "HTTP 502"
expect_lacks "failed search is not read as no match" "$got" "No open issue"

# gh's stderr is not a result: a warning on a good search is not a match,
# and a quiet failure is not called a timeout.
got=$(STUB_WARN="warning: token expires soon" STUB_ISSUES="#7 teach-lib: y" \
      context "$hook" w1 'gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y')
expect_has "a good search lists its matches" "$got" "#7 teach-lib: y"
expect_lacks "a stderr warning is not listed as a match" "$got" "token expires soon"
got=$(STUB_FAIL_QUIET=1 context "$hook" w2 'gh issue create --repo caneff/agent-skills --title "teach-lib: x" --body y')
expect_has "a quiet failure names its exit status" "$got" "failed" "exited 4"
expect_lacks "a quiet failure is not called a timeout" "$got" "timed out"

rm -f "$STUB_ARGS"
got=$(context "$hook" s5 "gh issue create --web")
expect_has "extraction: no title: says no search ran" "$got" "${section[@]}" "no search ran"
expect_no_gh "gh not run with no component"

expect_none "unrelated command" "$(context "$hook" s6 "gh issue list --label backlog")"
expect_none "trigger in a grep pattern" "$(context "$hook" s6 "rg 'x; gh issue create' file-ticket/")"
expect_none "trigger in a heredoc body" "$(context "$hook" s6 "cat > f.md <<'EOF2'
gh issue create --title x
EOF2")"

# The repo searched is the one the command files in, never text in its body.
git init -q "$tmp/other" && git -C "$tmp/other" remote add origin https://github.com/caneff/other.git
git init -q "$tmp/plain"
searched_repo() { # <want>: the stub's last --repo value
  local got
  got=$(grep -A1 -xF -- "--repo" "$STUB_ARGS" | tail -1)
  if [ "$got" = "$1" ]; then echo "PASS: searched $1"; else echo "FAIL: searched '$got', want '$1'"; fails=1; fi
}
export STUB_ISSUES="#9 other-thing: x"
got=$(context "$hook" r1 "cd $tmp/other && gh issue create --title 'other-thing: y' --body z")
expect_has "extraction: a cd before the create picks the repo" "$got" "${section[@]}" "in caneff/other"
searched_repo caneff/other
got=$(RUN_CWD="$tmp/other" context "$hook" r2 'gh issue create --title "other-thing: y" --body "see -R foo/bar"')
expect_has "extraction: a -R inside the body is text" "$got" "${section[@]}" "in caneff/other"
searched_repo caneff/other
got=$(RUN_CWD="$tmp/plain" context "$hook" r5 'gh issue create --title "other-thing: y" --body "see -R foo/bar" --repo caneff/other')
expect_has "extraction: the real --repo wins over a -R in the body" "$got" "in caneff/other"
searched_repo caneff/other
got=$(RUN_CWD="$tmp/plain" context "$hook" r6 'GH_REPO=caneff/other gh issue create --title "other-thing: y" --body z')
expect_has "extraction: a GH_REPO prefix names the repo" "$got" "in caneff/other"
searched_repo caneff/other
rm -f "$STUB_ARGS"
got=$(RUN_CWD="$tmp/plain" context "$hook" r3 'gh issue create --title "other-thing: y" --body z')
expect_has "no GitHub origin: says no search ran" "$got" "No repo could be read"
expect_no_gh "gh not run with no repo"
got=$(context "$hook" r4 "cd \"$tmp/other\" && gh issue create --title 'other-thing: y' --body z")
expect_has "a quoted cd path is not guessed at" "$got" "No repo could be read"

# A hook killed by its timeout printed nothing, so it spends nothing: the next
# filing in that session still gets the section.
printf '%s' 'gh issue create --repo caneff/agent-skills --title "a-b: c" --body d' \
  | jq -Rs '{session_id:"t1",cwd:"/",tool_input:{command:.}}' \
  | STUB_SLEEP=3 PATH="$STUB_PATH:$PATH" timeout 1 bash "$hook" >/dev/null 2>&1
expect_has "extraction: a killed hook spent nothing" \
  "$(context "$hook" t1 'gh issue create --repo caneff/agent-skills --title "a-b: c" --body d')" "${section[@]}"

copy_tree
sed -i 's/^## Before filing a ticket$/## Filing/' "$tmp/tree/claude/WORKFLOW.md"
got=$(context "$tmp/tree/claude/hooks/teach-filing.sh" s7 'gh issue create --title "a: b" --body c')
expect_has "renamed heading is reported, not silent" "$got" "Before filing a ticket" "not found"

finish
