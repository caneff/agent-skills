#!/usr/bin/env bash
# Safe wrapper around `npx skills update`: a git buffer makes every update
# reviewable and reversible, and skills listed in .protected-skills keep their
# local edits instead of being silently overwritten.
set -euo pipefail
SKILLS="${SKILLS_DIR:-$HOME/.agents/skills}"
cd "$SKILLS"
git(){ command git -c user.email=skills@local -c user.name=skills "$@"; }

# 1. git buffer — init on first run
if [ ! -d .git ]; then
  git init -q && git add -A && git commit -qm "baseline: skills as of $(date +%F)"
  echo "initialized git buffer in $SKILLS"
fi

# 2. snapshot current state (so PRE holds your edits)
git add -A
git commit -qm "pre-update snapshot $(date +%F)" >/dev/null 2>&1 || true
PRE=$(git rev-parse HEAD)

# 3. update through the package manager
echo "running: npx skills update -g"
npx -y skills update -g

# 4. record upstream result
git add -A
if ! git commit -qm "upstream: skills update $(date +%F)" >/dev/null 2>&1; then
  echo "no upstream changes."; exit 0
fi
POST=$(git rev-parse HEAD)

# 5. protect locally-edited skills: keep YOUR version, flag upstream delta
restored=()
if [ -f .protected-skills ]; then
  while read -r s; do
    [[ -z "$s" || "$s" == \#* ]] && continue
    if [ -e "$s" ] && ! git diff --quiet "$PRE" "$POST" -- "$s"; then
      git checkout "$PRE" -- "$s"; restored+=("$s")
    fi
  done < .protected-skills
fi
if [ ${#restored[@]} -gt 0 ]; then
  git add -A && git commit -qm "restore local edits to protected skills"
  echo
  echo "Protected skills changed upstream — your edits were KEPT. Review the upstream delta and merge by hand if wanted:"
  for s in "${restored[@]}"; do echo "  git -C $SKILLS diff $PRE $POST -- $s"; done
fi

# 6. summary
echo
echo "=== what changed (vs before update) ==="
git --no-pager diff --stat "$PRE" HEAD
echo
echo "undo everything:  git -C $SKILLS reset --hard $PRE"
