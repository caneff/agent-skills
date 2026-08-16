#!/usr/bin/env bash
# Behavioral test for the run-audits.sh index/--only/--out seam (#376): the
# --index path must rebuild the index over whatever reports already sit in an
# --out dir, WITHOUT running any audit or needing a full sweep to have run.
#
# No `claude` is invoked here: --index runs no audits, and AUDITS_NO_SYNTH=1
# skips the one synthesis call. So this test is hermetic and offline.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/run-audits.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Prepopulate two audits' reports as if prior `--only` runs had landed them.
for name in dead-code test-audit; do
  mkdir -p "$tmp/collection/$name"
  echo "<html><body>$name report</body></html>" >"$tmp/collection/$name/report.html"
done

# --index over the dir: rebuild the index, run nothing.
AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$tmp" >"$tmp/run.log" 2>&1 \
  || fail "--index run exited non-zero; see: $(cat "$tmp/run.log")"

index="$tmp/collection/index.html"
[ -f "$index" ] || fail "index.html was not built at $index"
grep -q "dead-code" "$index" || fail "index missing dead-code row"
grep -q "test-audit" "$index" || fail "index missing test-audit row"
grep -q 'dead-code/report.html' "$index" || fail "index missing link to dead-code report"

# --index must not have invoked any audit: no per-audit log should exist.
if compgen -G "$tmp/logs/*.log" >/dev/null; then
  fail "--index ran audits (found logs) — it must rebuild over existing reports only"
fi

echo "ok"

# --- report_path_from_log (#391): marker line wins over a split path in prose,
# and a legacy bare single-line path still works with no marker present. ---
source "$SCRIPT"

log="$tmp/split-with-marker.log"
cat >"$log" <<'EOF'
Artifacts in `/tmp/dead-code-1786905848/`:
- `report.html` (opened) — grouped summary.
ALL_AUDITS_REPORT=/tmp/dead-code-1786905848/report.html
EOF
got="$(report_path_from_log "$log")"
[ "$got" = "/tmp/dead-code-1786905848/report.html" ] \
  || fail "marker extraction: got '$got', want '/tmp/dead-code-1786905848/report.html'"

log="$tmp/legacy-bare-path.log"
cat >"$log" <<'EOF'
some preamble
report written to /tmp/ponytail-audit-123/report.html
EOF
got="$(report_path_from_log "$log")"
[ "$got" = "/tmp/ponytail-audit-123/report.html" ] \
  || fail "legacy fallback: got '$got', want '/tmp/ponytail-audit-123/report.html'"

log="$tmp/competing-path-plus-marker.log"
cat >"$log" <<'EOF'
See /tmp/other-dir/unrelated.html for background info.
ALL_AUDITS_REPORT=/tmp/dead-code-1786905848/report.html
EOF
got="$(report_path_from_log "$log")"
[ "$got" = "/tmp/dead-code-1786905848/report.html" ] \
  || fail "marker precedence: got '$got', want the marker's path, not the earlier stray .html"

echo "ok (report_path_from_log)"

# --- audit_prompt (#397): the prompt handed to `claude -p` must carry the
# same whole-repo override the SKILL.md fan-out gives its subagents, so a
# diff-oriented audit's default doesn't silently mismatch the sweep's scope.
got="$(audit_prompt dead-code /some/repo)"
case "$got" in
  '/dead-code /some/repo'*) : ;;
  *) fail "audit_prompt: missing/misplaced slash line; got: $got" ;;
esac
echo "$got" | grep -q '/some/repo' || fail "audit_prompt: missing repo path; got: $got"
echo "$got" | grep -qi 'ENTIRE repository' || fail "audit_prompt: missing whole-repo override marker; got: $got"
echo "$got" | grep -qi 'not a git diff' || fail "audit_prompt: missing not-a-diff marker; got: $got"

echo "ok (audit_prompt)"

# --- --mutation flag (#399): explicit-list selection, offline, no sweep ---

out="$(bash "$SCRIPT" --mutation a.py,b.py 2>&1)" || fail "--mutation a.py,b.py exited non-zero"
printf '%s\n' "$out" | grep -q '^mutation-target: a.py$' || fail "--mutation: missing target a.py; got: $out"
printf '%s\n' "$out" | grep -q '^mutation-target: b.py$' || fail "--mutation: missing target b.py; got: $out"
first_line="$(printf '%s\n' "$out" | grep -n '^mutation-target: a\.py$' | cut -d: -f1)"
second_line="$(printf '%s\n' "$out" | grep -n '^mutation-target: b\.py$' | cut -d: -f1)"
[ -n "$first_line" ] && [ -n "$second_line" ] && [ "$first_line" -lt "$second_line" ] \
  || fail "--mutation: a.py must be emitted before b.py; got: $out"

# --mutation must short-circuit before any audit sweep runs (mirrors --index test).
mtmp="$(mktemp -d)"
trap 'rm -rf "$mtmp"' RETURN 2>/dev/null || true
AUDITS_NO_SYNTH=1 bash "$SCRIPT" --mutation a.py,b.py --out "$mtmp" >"$mtmp/run.log" 2>&1 \
  || fail "--mutation --out exited non-zero; see: $(cat "$mtmp/run.log")"
if compgen -G "$mtmp/logs/*.log" >/dev/null; then
  fail "--mutation ran audits (found logs) — it must short-circuit before the sweep"
fi
rm -rf "$mtmp"

echo "ok (--mutation basic selection)"

out="$(bash "$SCRIPT" --mutation " a.py , , b.py " 2>&1)" || fail "--mutation with whitespace exited non-zero"
lines="$(printf '%s\n' "$out" | grep '^mutation-target: ')"
want="$(printf 'mutation-target: a.py\nmutation-target: b.py')"
[ "$lines" = "$want" ] || fail "--mutation whitespace trim: got '$lines', want '$want'"

echo "ok (--mutation whitespace trim + empty-drop)"

out="$(bash "$SCRIPT" --mutation "" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--mutation \"\" must exit 0, got $rc"
printf '%s\n' "$out" | grep -q '^mutation-target: ' && fail "--mutation \"\" must emit zero targets; got: $out"

out="$(bash "$SCRIPT" --mutation "  " 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--mutation \"  \" must exit 0, got $rc"
printf '%s\n' "$out" | grep -q '^mutation-target: ' && fail "--mutation \"  \" must emit zero targets; got: $out"

echo "ok (--mutation empty list is a no-op)"
