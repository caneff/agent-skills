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
echo "untouched by upstream" > myskill/del-clean.md
seq_lines > myskill/del-changed.md
seq_lines > "myskill/réf.md"          # non-ASCII: core.quotePath must not hide it
seq_lines > myskill/exec-merge.sh     # upstream keeps it 644, you chmod +x
seq_lines > myskill/modeonly.sh       # same bytes everywhere, you chmod +x
ln -s targetA myskill/link
git add -A; git commit -qm base
BASE=$(git rev-parse HEAD:myskill); BASE_C=$(git rev-parse HEAD)

# --- PRE: your local edits on top ------------------------------------------
sed -i 's/^line1$/line1 LOCAL/' myskill/SKILL.md
sed -i 's/^line5$/line5 LOCAL/' myskill/reference/overlap.md
echo "my own note" > myskill/local-only.md
printf '#!/bin/sh\necho mine\n' > myskill/local-only.sh; chmod +x myskill/local-only.sh
sed -i 's/^line1$/line1 LOCAL/' "myskill/réf.md"
sed -i 's/^line1$/line1 LOCAL/' myskill/exec-merge.sh; chmod +x myskill/exec-merge.sh
echo "both sides added this" > myskill/addadd.md
chmod +x myskill/modeonly.sh
ln -sfn targetLOCAL myskill/link
rm myskill/del-clean.md myskill/del-changed.md     # you deleted both
git add -A; git commit -qm local
PRE=$(git rev-parse HEAD)

# --- POST: what upstream published instead ---------------------------------
git checkout -q "$BASE_C" -- myskill   # upstream never saw your edits
sed -i 's/^line10$/line10 UPSTREAM/' myskill/SKILL.md
sed -i 's/^line5$/line5 UPSTREAM/' myskill/reference/overlap.md
echo "brand new" > myskill/new-upstream.md
sed -i 's/^line3$/line3 UPSTREAM/' myskill/del-changed.md   # upstream edited what you deleted
sed -i 's/^line10$/line10 UPSTREAM/' "myskill/réf.md"
sed -i 's/^line10$/line10 UPSTREAM/' myskill/exec-merge.sh
echo "upstream added it too" > myskill/addadd.md
ln -sfn targetUP myskill/link
rm myskill/local-only.md myskill/local-only.sh
chmod +x myskill/tool.sh
git add -A; git commit -qm upstream
POST=$(git rev-parse HEAD)

# working tree now holds POST, exactly as safe-update.sh leaves it
report=$WORK/report.txt; errlog=$WORK/stderr.txt
merge_skill myskill "$BASE" "$PRE" "$POST" > "$report" 2> "$errlog"
rc=$?
check "merge writes nothing to stderr" "" "$(cat "$errlog")"

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

# the merged file is exactly base plus both edits — nothing else moved
{ echo "line1 LOCAL"; for i in 2 3 4 5 6 7 8 9; do echo "line$i"; done; echo "line10 UPSTREAM"; } > "$WORK/want"
if diff -q "$WORK/want" myskill/SKILL.md >/dev/null; then ok "merged file is base plus both edits"
else bad "merged file is base plus both edits"; diff "$WORK/want" myskill/SKILL.md; fi

# untouched-by-you files take upstream; your unique files survive; new ones land
check "local-only file restored" "my own note" "$(cat myskill/local-only.md 2>/dev/null)"
contains "local-only reported" "LOCAL	local-only.md" "$report"
check "new upstream file kept" "brand new" "$(cat myskill/new-upstream.md 2>/dev/null)"
contains "new upstream file reported" "UPSTREAM	new-upstream.md" "$report"
if [ -x myskill/tool.sh ]; then ok "upstream mode change kept"; else bad "upstream mode change kept"; fi
# a restored local-only file keeps its executable bit (put writes the mode)
if [ -x myskill/local-only.sh ]; then ok "restored file keeps exec bit"; else bad "restored file keeps exec bit"; fi

# you deleted a file upstream left alone: the deletion stands
if [ -e myskill/del-clean.md ]; then bad "local deletion honoured"; else ok "local deletion honoured"; fi
contains "local deletion reported" "LOCAL	del-clean.md" "$report"
# you deleted a file upstream then changed: nobody wins silently
contains "delete-vs-edit conflicts" "CONFLICT	del-changed.md" "$report"
# ...and the report says which side is actually sitting in the tree, since a
# delete-vs-edit conflict has no lines to mark up
contains "delete-vs-edit names the surviving side" "upstream changed it, and ITS version is in the tree" "$report"

# a non-ASCII name must merge like any other (core.quotePath would hide it)
contains "non-ASCII file kept local hunk"    "line1 LOCAL"     "myskill/réf.md"
contains "non-ASCII file took upstream hunk" "line10 UPSTREAM" "myskill/réf.md"
contains "non-ASCII file reported" "MERGED	réf.md" "$report"

# a file both sides added has no base version — merge it against an empty one
contains "add/add conflicts" "CONFLICT	addadd.md" "$report"
contains "add/add keeps your line"     "both sides added this"  myskill/addadd.md
contains "add/add keeps upstream line" "upstream added it too"  myskill/addadd.md

# you chmod +x a file and nothing else changed: the mode is still your edit
if [ -x myskill/modeonly.sh ]; then ok "mode-only local edit survives"
else bad "mode-only local edit survives"; fi
contains "mode-only edit reported" "LOCAL	modeonly.sh" "$report"

# a symlink cannot be line-merged: yours stays a symlink, and writing through
# it must not spray content into whatever it points at
if [ -L myskill/link ]; then ok "conflicted symlink is still a symlink"
else bad "conflicted symlink is still a symlink"; fi
check "conflicted symlink keeps your target" "targetLOCAL" "$(readlink myskill/link 2>/dev/null)"
if [ -e myskill/targetUP ] || [ -e myskill/targetLOCAL ]; then
  bad "no file written through the symlink"
else ok "no file written through the symlink"; fi
contains "symlink conflict reported" "CONFLICT	link" "$report"

# you chmod +x a file, upstream edits its text: your mode is an edit too
contains "content-merged file merged" "MERGED	exec-merge.sh" "$report"
if [ -x myskill/exec-merge.sh ]; then ok "local exec bit survives a content merge"
else bad "local exec bit survives a content merge"; fi

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
