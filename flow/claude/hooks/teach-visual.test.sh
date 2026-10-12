#!/usr/bin/env bash
# Contract test for teach-visual.sh: the first `zed` or image-opener call
# (`wslview` and its kin) answers with VISUAL-INSPECTION.md § Showing me a
# file, the first `shot-scraper` call with § Reading a rendered page yourself,
# each once per session.
# Run: bash flow/claude/hooks/teach-visual.test.sh
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=teach-testlib.sh
. "$here/teach-testlib.sh"
hook="$here/teach-visual.sh"

# The extraction assertions: each heading the context names, plus a sentence
# from that section's body.
showing=(" § Showing me a file" "Open it for me; never print a path and ask me to open it.")
reading=(" § Reading a rendered page yourself" "Bare paths work — it prefixes \`file:\` itself.")

got=$(context "$hook" s1 "zed flow/claude/SHELL-SAFETY.md:12")
expect_has "extraction: zed returns § Showing me a file" "$got" "${showing[@]}"
expect_lacks "zed does not also return § Reading a rendered page yourself" "$got" "${reading[0]}"
expect_none "second zed in the same session" "$(context "$hook" s1 "zed README.md")"
got=$(context "$hook" s1 "shot-scraper accessibility report.html")
expect_has "extraction: shot-scraper returns § Reading a rendered page yourself" "$got" "${reading[@]}"
expect_none "second shot-scraper in the same session" "$(context "$hook" s1 "shot-scraper report.html -o a.png")"
expect_has "extraction: both triggers in one command, new session" \
  "$(context "$hook" s2 "shot-scraper page.html -o p.png && zed p.png")" "${showing[@]}" "${reading[@]}"

# The image openers share § Showing me a file with zed, once per session across
# all of them (#1531).
for opener in "wslview sheet-2.png" "xdg-open sheet.png" "explorer.exe sheet.png" "eog sheet.png" "feh sheet.png"; do
  sid="open-${opener%% *}"
  expect_has "extraction: ${opener%% *} returns § Showing me a file" \
    "$(context "$hook" "$sid" "$opener")" "${showing[@]}"
  expect_none "second ${opener%% *} in the same session" "$(context "$hook" "$sid" "$opener")"
done
expect_none "zed after wslview in the same session" "$(context "$hook" open-wslview "zed README.md")"
expect_has "wslview in a pipeline after a guard" "$(context "$hook" s5 "ls sheet.png && wslview sheet.png")" "${showing[@]}"
expect_none "opener as an argument" "$(context "$hook" s6 "which wslview")"
expect_none "opener in a grep pattern" "$(context "$hook" s6 "rg 'wslview' docs/")"

expect_none "unrelated command" "$(context "$hook" s3 "ls -la")"
expect_none "trigger in a grep pattern" "$(context "$hook" s3 "rg 'x; shot-scraper' docs/")"
expect_none "trigger in a heredoc body" "$(context "$hook" s3 "cat > open.sh <<'SH'
zed notes.md
SH")"
expect_none "trigger as an argument" "$(context "$hook" s3 "which zed")"

copy_tree
sed -i 's/^## Reading a rendered page yourself$/## Reading a page/' "$tmp/tree/claude/VISUAL-INSPECTION.md"
got=$(context "$tmp/tree/claude/hooks/teach-visual.sh" s4 "shot-scraper page.html")
expect_has "renamed heading is reported, not silent" "$got" "Reading a rendered page yourself" "not found"

finish
