#!/usr/bin/env bash
# #1693: the harness substitutes an invocation's arguments into a SKILL.md for
# `$1`, `$2`, ... — including inside its shell blocks. A block that carries
# `"$1"` therefore runs with the skill's args pasted in, or empty, and the
# capture it was meant to run gets retyped by hand. Shell that needs positional
# parameters lives in a script file the SKILL.md calls, never inline.
# Scans every fenced block of every tracked SKILL.md for `$<digit>` and
# `${<digit>` (`$0` included, since the harness's rule for it is not known);
# `$@`, `$#` and `$*` stay allowed. Prose outside a fenced block is not scanned.
# all.sh: prose-check (reads the tree's Markdown: a Markdown-only change in a directory with no suites runs it)
set -u
root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1
fail=0 files=0
while IFS= read -r f; do
  files=$((files + 1))
  hits=$(awk '
    /^[ \t]*```/ { inb = !inb; next }
    inb && /\$[0-9]|\$\{[0-9]/ { printf "%d: %s\n", NR, $0 }
  ' "$f")
  [ -z "$hits" ] || { printf 'FAIL: %s has a positional parameter in a fenced block:\n%s\n' "$f" "$hits"; fail=1; }
done < <(git ls-files -- 'SKILL.md' '*/SKILL.md' '**/SKILL.md')
[ "$files" -gt 0 ] || { echo "FAIL: no tracked SKILL.md found, so nothing was scanned"; exit 1; }
[ "$fail" -eq 0 ] && echo "ok: $files SKILL.md files carry no \$<digit> token in a fenced block"
exit "$fail"
