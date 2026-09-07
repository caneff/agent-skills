#!/usr/bin/env bash
# Three-way merge tests for safe-update.sh. Builds a throwaway git buffer that
# mirrors a real run — a base commit (the upstream version you installed), a
# local-edits commit (PRE), an upstream commit (POST) — then calls the merge
# helpers directly. safe-update.sh is sourced, so it must not run its update
# flow on source. No network, no npx.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
# Point the script at the fixture before sourcing, so a regression that makes
# sourcing execute the update cannot touch the real skills dir.
export SKILLS_DIR="$WORK"
# shellcheck source=safe-update.sh
source "$SCRIPT_DIR/safe-update.sh"
set +e   # the sourced script sets -e; these tests assert on exit codes

fails=0
ok(){ printf 'ok   %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
check(){ # <label> <expected> <actual>
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi
}
contains(){ # <label> <needle> <file>
  if grep -qF -- "$2" "$3"; then ok "$1"; else bad "$1 — [$2] not in $3"; fi
}
lacks(){ # <label> <needle> <file>
  if grep -qF -- "$2" "$3"; then bad "$1 — [$2] present in $3"; else ok "$1"; fi
}

cd "$WORK"
git init -q .

seq_lines(){ for i in $(seq 1 10); do echo "line$i"; done; }

# --- base: the upstream version that was installed -------------------------
mkdir -p myskill/reference
seq_lines > myskill/SKILL.md
seq_lines > myskill/reference/overlap.md
echo "upstream tool" > myskill/tool.sh
git add -A; git commit -qm base
BASE=$(git rev-parse HEAD:myskill); BASE_C=$(git rev-parse HEAD)

# --- PRE: your local edits on top ------------------------------------------
sed -i 's/^line1$/line1 LOCAL/' myskill/SKILL.md
sed -i 's/^line5$/line5 LOCAL/' myskill/reference/overlap.md
echo "my own note" > myskill/local-only.md
git add -A; git commit -qm local
PRE=$(git rev-parse HEAD)

# --- POST: what upstream published instead ---------------------------------
git checkout -q "$BASE_C" -- myskill   # upstream never saw your edits
sed -i 's/^line10$/line10 UPSTREAM/' myskill/SKILL.md
sed -i 's/^line5$/line5 UPSTREAM/' myskill/reference/overlap.md
echo "brand new" > myskill/new-upstream.md
rm myskill/local-only.md
chmod +x myskill/tool.sh
git add -A; git commit -qm upstream
POST=$(git rev-parse HEAD)

# working tree now holds POST, exactly as safe-update.sh leaves it
report=$WORK/report.txt
merge_skill myskill "$BASE" "$PRE" "$POST" > "$report"
rc=$?

check "conflicting skill exits non-zero" 1 "$rc"

# AC1: non-overlapping hunks merge, both sides present, no markers
contains "local hunk kept"    "line1 LOCAL"    myskill/SKILL.md
contains "upstream hunk taken" "line10 UPSTREAM" myskill/SKILL.md
lacks    "clean file has no markers" "<<<<<<<" myskill/SKILL.md
contains "clean merge reported" "MERGED	SKILL.md" "$report"

# AC2: overlapping hunks leave conflict markers and are named in the report
contains "conflict markers written" "<<<<<<<" myskill/reference/overlap.md
contains "conflict names local side"    "line5 LOCAL"    myskill/reference/overlap.md
contains "conflict names upstream side" "line5 UPSTREAM" myskill/reference/overlap.md
contains "conflict reported" "CONFLICT	reference/overlap.md" "$report"

# untouched-by-you files take upstream; your unique files survive; new ones land
check "local-only file restored" "my own note" "$(cat myskill/local-only.md 2>/dev/null)"
contains "local-only reported" "LOCAL	local-only.md" "$report"
check "new upstream file kept" "brand new" "$(cat myskill/new-upstream.md 2>/dev/null)"
if [ -x myskill/tool.sh ]; then ok "upstream mode change kept"; else bad "upstream mode change kept"; fi

# A skill you edited that upstream only reformatted merges clean and exits 0
mkdir -p clean/reference
seq_lines > clean/SKILL.md
git add -A; git commit -qm "clean base"
CBASE=$(git rev-parse HEAD:clean); CBASE_C=$(git rev-parse HEAD)
sed -i 's/^line2$/line2 LOCAL/' clean/SKILL.md
git add -A; git commit -qm "clean local"
CPRE=$(git rev-parse HEAD)
git checkout -q "$CBASE_C" -- clean
sed -i 's/^line9$/line9 UPSTREAM/' clean/SKILL.md
git add -A; git commit -qm "clean upstream"
CPOST=$(git rev-parse HEAD)
merge_skill clean "$CBASE" "$CPRE" "$CPOST" > "$WORK/clean.txt"
check "clean skill exits zero" 0 $?
contains "clean skill kept local"    "line2 LOCAL"    clean/SKILL.md
contains "clean skill took upstream" "line9 UPSTREAM" clean/SKILL.md

# --- base lookup -----------------------------------------------------------
found=$(resolve_base_tree "$BASE") ; check "base tree resolves" "$BASE" "$found"
if resolve_base_tree 0000000000000000000000000000000000000000 >/dev/null 2>&1; then
  bad "missing base tree reports failure"
else
  ok "missing base tree reports failure"
fi
if resolve_base_tree "" >/dev/null 2>&1; then
  bad "empty base hash reports failure"
else
  ok "empty base hash reports failure"
fi

[ "$fails" -eq 0 ] || { echo "$fails failure(s)"; exit 1; }
echo "all merge tests passed"
