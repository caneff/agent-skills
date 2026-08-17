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
AUDITS_NO_OPEN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$tmp" >"$tmp/run.log" 2>&1 \
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

out="$(MUTATION_DRY_RUN=1 bash "$SCRIPT" --mutation a.py,b.py 2>&1)" || fail "--mutation a.py,b.py exited non-zero"
printf '%s\n' "$out" | grep -q '^mutation-target: a.py$' || fail "--mutation: missing target a.py; got: $out"
printf '%s\n' "$out" | grep -q '^mutation-target: b.py$' || fail "--mutation: missing target b.py; got: $out"
first_line="$(printf '%s\n' "$out" | grep -n '^mutation-target: a\.py$' | cut -d: -f1)"
second_line="$(printf '%s\n' "$out" | grep -n '^mutation-target: b\.py$' | cut -d: -f1)"
[ -n "$first_line" ] && [ -n "$second_line" ] && [ "$first_line" -lt "$second_line" ] \
  || fail "--mutation: a.py must be emitted before b.py; got: $out"

# --mutation must short-circuit before any audit sweep runs (mirrors --index test).
mtmp="$(mktemp -d)"
trap 'rm -rf "$mtmp"' RETURN 2>/dev/null || true
MUTATION_DRY_RUN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --mutation a.py,b.py --out "$mtmp" >"$mtmp/run.log" 2>&1 \
  || fail "--mutation --out exited non-zero; see: $(cat "$mtmp/run.log")"
if compgen -G "$mtmp/logs/*.log" >/dev/null; then
  fail "--mutation ran audits (found logs) — it must short-circuit before the sweep"
fi
rm -rf "$mtmp"

echo "ok (--mutation basic selection)"

out="$(MUTATION_DRY_RUN=1 bash "$SCRIPT" --mutation " a.py , , b.py " 2>&1)" || fail "--mutation with whitespace exited non-zero"
lines="$(printf '%s\n' "$out" | grep '^mutation-target: ')"
want="$(printf 'mutation-target: a.py\nmutation-target: b.py')"
[ "$lines" = "$want" ] || fail "--mutation whitespace trim: got '$lines', want '$want'"

echo "ok (--mutation whitespace trim + empty-drop)"

# #400 changes what an empty list means: it now triggers the auto-select
# pre-pass instead of a silent zero-target no-op. Under AUDITS_NO_SYNTH=1 the
# pre-pass itself is skipped (mirrors the synthesis-pass gate), so empty list
# + AUDITS_NO_SYNTH=1 = no pre-pass = zero targets, and no `claude` ever runs
# — keeping this suite hermetic.
out="$(MUTATION_DRY_RUN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --mutation "" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--mutation \"\" (AUDITS_NO_SYNTH=1) must exit 0, got $rc"
printf '%s\n' "$out" | grep -q '^mutation-target: ' && fail "--mutation \"\" under AUDITS_NO_SYNTH=1 must emit zero targets; got: $out"

out="$(MUTATION_DRY_RUN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --mutation "  " 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--mutation \"  \" (AUDITS_NO_SYNTH=1) must exit 0, got $rc"
printf '%s\n' "$out" | grep -q '^mutation-target: ' && fail "--mutation \"  \" under AUDITS_NO_SYNTH=1 must emit zero targets; got: $out"

echo "ok (--mutation empty list under AUDITS_NO_SYNTH=1 skips the pre-pass, no claude)"

# --- mutation_cap pure function (#400): (candidates, N) -> (capped,
# skipped_count), offline, no subprocess/claude. ---

out="$(mutation_cap 3 a b c d e)"
skipped="$(printf '%s\n' "$out" | mutation_cap_skipped)"
capped="$(printf '%s\n' "$out" | mutation_cap_targets)"
[ "$skipped" = "2" ] || fail "mutation_cap: want skipped=2 for 5 candidates capped at 3, got '$skipped'"
want="$(printf 'a\nb\nc')"
[ "$capped" = "$want" ] || fail "mutation_cap: want capped='$want', got '$capped'"

out="$(mutation_cap 5 a b c)"
skipped="$(printf '%s\n' "$out" | mutation_cap_skipped)"
capped="$(printf '%s\n' "$out" | mutation_cap_targets)"
[ "$skipped" = "0" ] || fail "mutation_cap: want skipped=0 when list <= N, got '$skipped'"
want="$(printf 'a\nb\nc')"
[ "$capped" = "$want" ] || fail "mutation_cap: list <= N must pass through unchanged, got '$capped'"

echo "ok (mutation_cap pure function)"

# --- --mutation auto-select pre-pass, offline via MUTATION_CANDIDATES injection
# (#400): the real candidate source is claude, but the cap + skip-line
# behavior around it must be testable without a subprocess. ---

# > N candidates: capped to default N=10, visible skip line naming the count.
twelve="$(for i in $(seq 1 12); do printf 'm%d.py\n' "$i"; done)"
out="$(MUTATION_DRY_RUN=1 MUTATION_CANDIDATES="$twelve" bash "$SCRIPT" --mutation 2>&1)"
count="$(printf '%s\n' "$out" | grep -c '^mutation-target: ')"
[ "$count" -eq 10 ] || fail "--mutation auto-select: want 10 capped targets, got $count; out: $out"
printf '%s\n' "$out" | grep -q '2 more modules skipped (raise MUTATION_MAX to include them)' \
  || fail "--mutation auto-select: missing visible skip line; got: $out"

# <= N candidates: unchanged, no skip line.
out="$(MUTATION_DRY_RUN=1 MUTATION_CANDIDATES=$'m1.py\nm2.py' bash "$SCRIPT" --mutation 2>&1)"
count="$(printf '%s\n' "$out" | grep -c '^mutation-target: ')"
[ "$count" -eq 2 ] || fail "--mutation auto-select: want 2 targets for a 2-candidate list, got $count; out: $out"
printf '%s\n' "$out" | grep -q 'more modules skipped' \
  && fail "--mutation auto-select: unexpected skip line for a list <= N; got: $out"

echo "ok (--mutation auto-select pre-pass: cap truncates, skip line, no line under cap)"

# MUTATION_MAX overrides the default N=10.
out="$(MUTATION_DRY_RUN=1 MUTATION_CANDIDATES=$'m1.py\nm2.py\nm3.py' MUTATION_MAX=2 bash "$SCRIPT" --mutation 2>&1)"
count="$(printf '%s\n' "$out" | grep -c '^mutation-target: ')"
[ "$count" -eq 2 ] || fail "MUTATION_MAX=2: want 2 targets, got $count; out: $out"
printf '%s\n' "$out" | grep -q '1 more modules skipped (raise MUTATION_MAX to include them)' \
  || fail "MUTATION_MAX=2: missing skip line naming 1 skipped; got: $out"

echo "ok (MUTATION_MAX overrides default cap)"

# --- auto-open guard: --index must not launch a browser under AUDITS_NO_OPEN=1.
# A fake `xdg-open` on PATH records that it fired; with the guard set it must
# never run, so the index rebuild in tests (and unattended sweeps) stops
# hijacking the user's window.
gtmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gtmp"' EXIT
mkdir -p "$gtmp/collection/dead-code" "$gtmp/bin"
echo '<html>x</html>' >"$gtmp/collection/dead-code/report.html"
cat >"$gtmp/bin/xdg-open" <<'SH'
#!/usr/bin/env bash
echo fired >>"$OPEN_SENTINEL"
SH
chmod +x "$gtmp/bin/xdg-open"
OPEN_SENTINEL="$gtmp/opened" PATH="$gtmp/bin:$PATH" \
  AUDITS_NO_OPEN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$gtmp" >/dev/null 2>&1 \
  || fail "guarded --index run exited non-zero"
[ -f "$gtmp/opened" ] && fail "xdg-open fired despite AUDITS_NO_OPEN=1"

echo "ok (--index honors AUDITS_NO_OPEN)"

# --- module_slug (#401): a module path becomes one safe, collision-free
# collection dir name — no nested dirs, no traversal. ---
[ "$(module_slug 'foo/bar.py')" = "foo_bar.py" ] || fail "module_slug: nested path; got '$(module_slug 'foo/bar.py')'"
[ "$(module_slug 'bar.py')" = "bar.py" ] || fail "module_slug: bare path; got '$(module_slug 'bar.py')'"
[ "$(module_slug 'a/b/c.py')" = "a_b_c.py" ] || fail "module_slug: deep path; got '$(module_slug 'a/b/c.py')'"

echo "ok (module_slug)"

# --- collect_module_report (#401, THE hermetic seam): given a worktree
# containing a mutation report, it lands at collection/<module>/ with its
# assets, honoring #391's path contract — both the ALL_AUDITS_REPORT= marker
# form and the legacy bare-path form. Offline, no claude, no real worktree. ---
ctmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gtmp" "$ctmp"' EXIT

# Marker form.
wt="$ctmp/fake-worktree-marker"
mkdir -p "$wt/assets"
echo '<html>report</html>' >"$wt/report.html"
echo '{"finding":1}' >"$wt/findings.jsonl"
echo 'marker-asset' >"$wt/assets/base.css"
log="$ctmp/marker.log"
printf 'some prose\nALL_AUDITS_REPORT=%s/report.html\n' "$wt" >"$log"
coll="$ctmp/collection"
mkdir -p "$coll"
collect_module_report "$log" "$coll" "foo/bar.py"
[ -f "$coll/foo_bar.py/report.html" ] || fail "collect_module_report (marker): report.html missing"
[ -f "$coll/foo_bar.py/findings.jsonl" ] || fail "collect_module_report (marker): findings.jsonl missing"
[ -f "$coll/foo_bar.py/assets/base.css" ] || fail "collect_module_report (marker): assets not carried"

# Bare-path (legacy) form — same worktree, different module name to avoid
# clobbering the prior assertion's directory.
log2="$ctmp/bare.log"
printf 'report written to %s/report.html\n' "$wt" >"$log2"
collect_module_report "$log2" "$coll" "baz.py"
[ -f "$coll/baz.py/report.html" ] || fail "collect_module_report (bare path): report.html missing"
[ -f "$coll/baz.py/findings.jsonl" ] || fail "collect_module_report (bare path): findings.jsonl missing"

echo "ok (collect_module_report)"

# --- mutation sub-index + main-index mutation row (#402): with mutation
# report dirs present in the collection, the index build renders exactly one
# `mutation` row on the main index (linking to mutation/index.html, not to
# any single module) plus a mutation/index.html sub-index listing one row
# per module with killed/total, survivor count, and a working relative link
# to that module's report.html. No mutation reports -> no row, no sub-index.
# Offline throughout (AUDITS_NO_SYNTH=1, AUDITS_NO_OPEN=1, --index runs no
# audits and no claude).
mutmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gtmp" "$ctmp" "$mutmp"' EXIT

for name in dead-code test-audit; do
  mkdir -p "$mutmp/collection/$name"
  echo "<html><body>$name report</body></html>" >"$mutmp/collection/$name/report.html"
done

mkdir -p "$mutmp/collection/solver.py"
echo '<html><body>solver report</body></html>' >"$mutmp/collection/solver.py/report.html"
cat >"$mutmp/collection/solver.py/findings.jsonl" <<'EOF'
{"bucket": "rewrite", "file": "solver.py", "line": 12, "category": "surviving-mutant", "summary": "s1", "failure": "f1", "extra": {"mutant": "solver.x__mutmut_1", "killed": false, "survived": true, "killed_count": 8, "survived_count": 2, "no_coverage_count": 0}}
EOF

mkdir -p "$mutmp/collection/oracle.py"
echo '<html><body>oracle report</body></html>' >"$mutmp/collection/oracle.py/report.html"
cat >"$mutmp/collection/oracle.py/findings.jsonl" <<'EOF'
{"bucket": "rewrite", "file": "oracle.py", "line": 3, "category": "surviving-mutant", "summary": "s2", "failure": "f2", "extra": {"mutant": "oracle.y__mutmut_1", "killed": false, "survived": true, "killed_count": 5, "survived_count": 1, "no_coverage_count": 2}}
EOF

AUDITS_NO_OPEN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$mutmp" >"$mutmp/run.log" 2>&1 \
  || fail "--index (with mutation dirs) exited non-zero; see: $(cat "$mutmp/run.log")"

muindex="$mutmp/collection/index.html"
[ -f "$muindex" ] || fail "index.html was not built at $muindex"

mutation_rows="$(grep -c '<td>mutation</td>' "$muindex" || true)"
[ "$mutation_rows" = "1" ] || fail "main index must have exactly ONE mutation row, got $mutation_rows"
grep -q 'href="mutation/index.html"' "$muindex" || fail "main index mutation row must link to mutation/index.html"
grep -q 'href="solver.py/report.html"' "$muindex" && fail "main index must not link directly to a single module's report"

subindex="$mutmp/collection/mutation/index.html"
[ -f "$subindex" ] || fail "mutation/index.html sub-index was not built at $subindex"
grep -q 'solver.py' "$subindex" || fail "sub-index missing solver.py row"
grep -q 'oracle.py' "$subindex" || fail "sub-index missing oracle.py row"
grep -q 'href="../solver.py/report.html"' "$subindex" || fail "sub-index missing working link to solver.py's report.html"
grep -q 'href="../oracle.py/report.html"' "$subindex" || fail "sub-index missing working link to oracle.py's report.html"
grep -q '8/10' "$subindex" || fail "sub-index missing solver.py killed/total tally (8/10)"
grep -q '5/8' "$subindex" || fail "sub-index missing oracle.py killed/total tally (5/8)"
grep -q '../assets/base/base.css' "$subindex" || fail "sub-index must reuse the base spine (relative assets path)"

# --index must not have invoked any audit for the mutation-index build either.
if compgen -G "$mutmp/logs/*.log" >/dev/null; then
  fail "--index (mutation) ran audits (found logs) — it must rebuild over existing reports only"
fi

echo "ok (mutation sub-index + single main-index mutation row)"

# --- no-test modules: a worthy source module with zero tests can't be
# mutated, so the --mutation run records it into the collection as a
# mutation-no-tests.json entry (no mutmut run). The index build must surface it
# LOUDLY: a distinct "no tests" section in the sub-index, the repo-wide
# "N of M source modules have no tests" stat, the main-index mutation-row
# verdict reflecting the no-test count, and — for a module that WAS mutated —
# the killed / weak-assertion / no-coverage counts kept separable, not merged
# into one survivor number. Offline throughout.
nttmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gtmp" "$ctmp" "$mutmp" "$nttmp"' EXIT

mkdir -p "$nttmp/collection/solver.py"
echo '<html><body>solver report</body></html>' >"$nttmp/collection/solver.py/report.html"
# solver: 8 killed, 2 weak-assertion survivors, 3 no-coverage survivors.
cat >"$nttmp/collection/solver.py/findings.jsonl" <<'EOF'
{"bucket": "rewrite", "file": "solver.py", "line": 12, "category": "surviving-mutant", "summary": "s1", "failure": "f1", "extra": {"mutant": "solver.x__mutmut_1", "killed": false, "survived": true, "killed_count": 8, "survived_count": 2, "no_coverage_count": 3}}
EOF
# Two worthy modules with no tests at all, plus the repo-wide worthy total.
cat >"$nttmp/collection/mutation-no-tests.json" <<'EOF'
{"no_tests": ["widget.py", "gadget.py"], "total": 6}
EOF

AUDITS_NO_OPEN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$nttmp" >"$nttmp/run.log" 2>&1 \
  || fail "--index (no-test modules) exited non-zero; see: $(cat "$nttmp/run.log")"

ntindex="$nttmp/collection/index.html"
ntsub="$nttmp/collection/mutation/index.html"
[ -f "$ntsub" ] || fail "no-test: sub-index was not built at $ntsub"

# Main-index mutation-row verdict reflects the no-test count.
grep -q 'with no tests' "$ntindex" || fail "main index mutation row must report the no-test count"
grep -qE '2 with no tests' "$ntindex" || fail "main index must count both no-test modules (2)"

# Repo-wide stat.
grep -qE '2 of 6 source modules have no tests' "$ntsub" || fail "sub-index missing repo-wide 'N of M source modules have no tests' stat"

# Distinct no-test section listing each testless module.
grep -q 'widget.py' "$ntsub" || fail "sub-index missing no-test module widget.py"
grep -q 'gadget.py' "$ntsub" || fail "sub-index missing no-test module gadget.py"
grep -qi 'no tests' "$ntsub" || fail "sub-index missing a distinct 'no tests' section"

# solver was mutated: killed/total (8/13) present, and weak (2) vs no-coverage
# (3) kept SEPARABLE — not merged into a single '5 survivors'.
grep -q '8/13' "$ntsub" || fail "sub-index missing solver killed/total (8/13)"
grep -qiE 'weak' "$ntsub" || fail "sub-index must label a weak-assertion column"
grep -qiE 'no.?coverage' "$ntsub" || fail "sub-index must label a no-coverage column distinctly from weak-assertion"

echo "ok (no-test modules: distinct section, stat, verdict, weak/no-coverage split)"

# --- negative: no mutation report dirs -> no mutation row, no sub-index ---
negtmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gtmp" "$ctmp" "$mutmp" "$nttmp" "$negtmp"' EXIT

for name in dead-code test-audit; do
  mkdir -p "$negtmp/collection/$name"
  echo "<html><body>$name report</body></html>" >"$negtmp/collection/$name/report.html"
done

AUDITS_NO_OPEN=1 AUDITS_NO_SYNTH=1 bash "$SCRIPT" --index --out "$negtmp" >"$negtmp/run.log" 2>&1 \
  || fail "--index (no mutation dirs) exited non-zero; see: $(cat "$negtmp/run.log")"

negindex="$negtmp/collection/index.html"
[ -f "$negindex" ] || fail "index.html was not built at $negindex"
grep -q '<td>mutation</td>' "$negindex" && fail "no mutation reports present but main index has a mutation row"
[ -e "$negtmp/collection/mutation" ] && fail "no mutation reports present but mutation/ sub-index was created"

echo "ok (no mutation reports -> no row, no sub-index)"
