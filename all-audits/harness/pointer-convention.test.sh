#!/usr/bin/env bash
# No audit skill doc restates AUDIT-RUN.md's write-and-deliver mechanics
# (#557, #610) — each points at it instead. A paraphrase names
# findings.jsonl, report.html, and the tmpdir (`<tmpdir>` or `$TMPDIR`)
# close together, regardless of the exact sentence used to connect them —
# that's the shape this test looks for, not one fixed sentence. A file that
# happens to mention the three terms far apart for unrelated reasons
# (crap-audit resolves `<tmpdir>` once for its own scratch files, well away
# from where it names its own output files) is not a paraphrase and must
# not trip this.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WINDOW=20
fail() { echo "FAIL: $*" >&2; exit 1; }

violations=""

while IFS= read -r -d '' f; do
  case "$f" in
    "$HERE"/*) continue ;;  # all-audits/harness owns the canonical paragraph
  esac

  mapfile -t jsonl_lines < <(grep -n 'findings\.jsonl' "$f" | cut -d: -f1)
  mapfile -t html_lines < <(grep -n 'report\.html' "$f" | cut -d: -f1)
  mapfile -t tmpdir_lines < <(grep -nE '\$TMPDIR|<tmpdir>' "$f" | cut -d: -f1)

  [ "${#jsonl_lines[@]}" -gt 0 ] && [ "${#html_lines[@]}" -gt 0 ] && [ "${#tmpdir_lines[@]}" -gt 0 ] || continue

  for a in "${jsonl_lines[@]}"; do
    for b in "${html_lines[@]}"; do
      for c in "${tmpdir_lines[@]}"; do
        lo=$a; hi=$a
        for n in "$b" "$c"; do
          [ "$n" -lt "$lo" ] && lo=$n
          [ "$n" -gt "$hi" ] && hi=$n
        done
        if [ $((hi - lo)) -le "$WINDOW" ]; then
          violations="$violations$f"$'\n'
        fi
      done
    done
  done
done < <(find "$ROOT" -name SKILL.md -print0)

[ -z "$violations" ] || fail "names findings.jsonl, report.html and the tmpdir within $WINDOW lines of each other instead of pointing at AUDIT-RUN.md:
$(printf '%s' "$violations" | sort -u)"

echo "ok"
