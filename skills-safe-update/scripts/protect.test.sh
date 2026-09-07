#!/usr/bin/env bash
# End-to-end tests for safe-update.sh's protection loop — the part merge.test.sh
# does not reach: which skills get protected, what a manual .protected-skills
# entry does, what happens when a merge breaks, and above all WHETHER THE BUFFER
# COMMITS. Each case builds its own throwaway skills dir; SKILLS_DIR points at
# that fixture, never at the real ~/.agents/skills. No npx, no network.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK=$(mktemp -d); trap 'chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
export SKILLS_DIR="$WORK"
# shellcheck source=safe-update.sh
source "$SCRIPT_DIR/safe-update.sh"
set +e   # the sourced script sets -e; these tests assert on exit codes

fails=0
ok(){ printf 'ok   %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi; }

seq_lines(){ for i in $(seq 1 10); do echo "line$i"; done; }

# Builds a skills-dir buffer in $1: a lock-era version of each named skill, your
# edits on top (PRE), then upstream's own change (POST). Leaves the shell inside
# it, sets PRE/POST, and writes the prelock (name<TAB>base tree sha) to
# $1/prelock. $2... are "<skill>:<local sed>:<upstream sed>" triples.
# Called in the current shell, never a subshell: the cd has to stick.
fixture(){
  local dir=$1; shift
  mkdir -p "$dir"; cd "$dir" || return 1
  git init -q .
  local spec skill
  for spec in "$@"; do
    skill=${spec%%:*}; mkdir -p "$skill"; seq_lines > "$skill/SKILL.md"
  done
  git add -A; git commit -qm base
  : > prelock
  for spec in "$@"; do
    skill=${spec%%:*}
    printf '%s\t%s\n' "$skill" "$(git rev-parse "HEAD:$skill")" >> prelock
  done
  local BASE_C; BASE_C=$(git rev-parse HEAD)
  for spec in "$@"; do
    skill=${spec%%:*}; sed -i "$(echo "$spec" | cut -d: -f2)" "$skill/SKILL.md"
  done
  git add -A; git commit -qm local
  PRE=$(git rev-parse HEAD)
  for spec in "$@"; do
    skill=${spec%%:*}
    git checkout -q "$BASE_C" -- "$skill"
    sed -i "$(echo "$spec" | cut -d: -f3)" "$skill/SKILL.md"
  done
  git add -A; git commit -qm upstream
  POST=$(git rev-parse HEAD)
  PRELOCK=$dir/prelock
}

# --- 1. a clean merge commits ----------------------------------------------
fixture "$WORK/clean" "alpha:s/^line1$/line1 LOCAL/:s/^line9$/line9 UP/"
head_before=$(git rev-parse HEAD)
protect_skills "$PRE" "$POST" "$PRELOCK"
check "clean merge is detected as merged" "alpha" "${merged[*]:-}"
check "clean merge leaves nothing conflicted" "" "${conflicted[*]:-}"
if [ "$(git rev-parse HEAD)" != "$head_before" ]; then ok "clean merge commits"
else bad "clean merge commits"; fi
check "clean merge leaves a clean tree" "" "$(git status --porcelain)"

# --- 2. a conflict must NOT commit, and must leave the markers in the tree ---
fixture "$WORK/conflict" "beta:s/^line5$/line5 LOCAL/:s/^line5$/line5 UP/"
head_before=$(git rev-parse HEAD)
protect_skills "$PRE" "$POST" "$PRELOCK"
check "conflict is detected" "beta" "${conflicted[*]:-}"
check "NOTHING is committed while a conflict stands" "$head_before" "$(git rev-parse HEAD)"
if [ -n "$(git status --porcelain)" ]; then ok "the merge is left in the working tree"
else bad "the merge is left in the working tree"; fi
if grep -q '<<<<<<<' beta/SKILL.md; then ok "markers are left for the hand merge"
else bad "markers are left for the hand merge"; fi
if git grep -q '<<<<<<<' HEAD -- beta 2>/dev/null; then bad "no markers reach a commit"
else ok "no markers reach a commit"; fi
# ...and resolving by hand is all it takes to commit
sed -i '/^[<=>]\{7\}/d' beta/SKILL.md
git add -A && git commit -qm resolved >/dev/null 2>&1
check "resolving by hand leaves a clean tree" "" "$(git status --porcelain)"

# --- 3. one conflict blocks the commit for every skill in the run -----------
fixture "$WORK/mixed" \
  "good:s/^line1$/line1 LOCAL/:s/^line9$/line9 UP/" \
  "bad:s/^line5$/line5 LOCAL/:s/^line5$/line5 UP/"
head_before=$(git rev-parse HEAD)
protect_skills "$PRE" "$POST" "$PRELOCK"
check "the clean skill still merged" "good" "${merged[*]:-}"
check "the conflicted one is named" "bad" "${conflicted[*]:-}"
check "a single conflict blocks the whole commit" "$head_before" "$(git rev-parse HEAD)"

# --- 4. .protected-skills forces a whole-file keep, never a merge ------------
fixture "$WORK/manual" "gamma:s/^line1$/line1 LOCAL/:s/^line9$/line9 UP/"
printf 'gamma' > .protected-skills   # deliberately unterminated: a hand-edited file often is
protect_skills "$PRE" "$POST" "$PRELOCK"
check "a manual entry is kept, not merged" "gamma" "${nobase[*]:-}"
check "a manual entry never merges" "" "${merged[*]:-}"
if grep -q 'line9 UP' gamma/SKILL.md; then bad "upstream delta is not applied to a kept skill"
else ok "upstream delta is not applied to a kept skill"; fi

# --- 5. a skill upstream deleted outright is kept, not lost -----------------
fixture "$WORK/deleted" "eps:s/^line1$/line1 LOCAL/:s/^line9$/line9 UP/"
git rm -rq eps && git commit -qm "upstream drops the skill" && POST=$(git rev-parse HEAD)
protect_skills "$PRE" "$POST" "$PRELOCK"
check "a deleted-upstream skill is kept" "eps" "${nobase[*]:-}"
if grep -q 'line1 LOCAL' eps/SKILL.md 2>/dev/null; then ok "your copy of it survives"
else bad "your copy of it survives"; fi

# --- 6. an unedited skill is left alone entirely -----------------------------
fixture "$WORK/unedited" "zeta:s/^line1$/line1/:s/^line9$/line9 UP/"
protect_skills "$PRE" "$POST" "$PRELOCK"
check "an unedited skill is not protected" "" "${merged[*]:-}${conflicted[*]:-}${nobase[*]:-}"

# --- 7. a skill upstream only chmod'd gets no empty report block ------------
fixture "$WORK/modeonly" "theta:s/^line1$/line1 LOCAL/:s/^line1$/line1 LOCAL/"
chmod +x theta/SKILL.md; git add -A; git commit -qm "upstream flips a mode"
POST=$(git rev-parse HEAD)
protect_skills "$PRE" "$POST" "$PRELOCK"
check "a mode-only upstream change still merges" "theta" "${merged[*]:-}"
check "and prints no empty report block" "" "$report"

# --- 8. a merge that cannot write keeps your version rather than half of it --
fixture "$WORK/broken" "eta:s/^line1$/line1 LOCAL/:s/^line9$/line9 UP/"
chmod a-w eta
protect_skills "$PRE" "$POST" "$PRELOCK" 2>/dev/null
chmod u+w eta
check "a broken merge falls back to keeping yours" "eta" "${nobase[*]:-}"
check "a broken merge is never reported as merged" "" "${merged[*]:-}"

[ "$fails" -eq 0 ] || { echo "$fails failure(s)"; exit 1; }
echo "all protection tests passed"
