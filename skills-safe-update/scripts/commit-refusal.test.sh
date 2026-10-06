#!/usr/bin/env bash
# Runs safe-update.sh's main() end to end against a fixture buffer with a fake
# `npx`, to prove a refused commit is never read as "nothing to commit" (#1450).
# The script used to force `-c user.email=skills@local`, which the checkout's
# commit-identity guard refuses; it then swallowed the refusal twice (the
# snapshot commit ended in `|| true`, the upstream commit's failure printed
# "no upstream changes." and exited 0). No network; every repo is under $WORK.
set -uo pipefail
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/safe-update.sh"
here="$(dirname "$SCRIPT")"
. "$here/../../tests/fixture-identity.sh"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT

fails=0
ok(){ printf 'ok   %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi; }

# fake npx: what `npx skills update -g` does to the tree, chosen per case by
# $FAKE_NPX (change = rewrite a skill file, none = leave the tree alone).
mkdir -p "$WORK/bin"
cat > "$WORK/bin/npx" <<'EOF'
#!/usr/bin/env bash
[ "${FAKE_NPX:-none}" = change ] && echo upstream > "$SKILLS_DIR/a/SKILL.md"
exit 0
EOF
chmod +x "$WORK/bin/npx"

# fixture <name> — a committed buffer with identity "t <t@example.com>".
fixture(){
  local d="$WORK/$1/skills"
  mkdir -p "$d/a"; echo base > "$d/a/SKILL.md"
  echo "{\"version\":3,\"skills\":{}}" > "$WORK/$1/.skill-lock.json"
  git -C "$d" init -q . && fixture_identity "$d" "$WORK" || return 1
  git -C "$d" add -A && git -C "$d" commit -qm base
  echo "$d"
}
refuse_hook(){ printf '#!/bin/sh\necho "REFUSED-BY-HOOK" >&2\nexit 1\n' > "$1/.git/hooks/pre-commit"; chmod +x "$1/.git/hooks/pre-commit"; }
run(){ # run <skills-dir> <FAKE_NPX> — sets OUT, RC
  OUT=$(SKILLS_DIR=$1 SKILL_LOCK=$1/../.skill-lock.json FAKE_NPX=$2 PATH="$WORK/bin:$PATH" \
        bash "$SCRIPT" 2>&1); RC=$?
}

# 1. refused snapshot commit (local edit pending): non-zero, hook's stderr shown
d=$(fixture refuse-snapshot); refuse_hook "$d"; echo edit > "$d/a/SKILL.md"
run "$d" none
[ "$RC" -ne 0 ] && ok "refused snapshot commit exits non-zero" || bad "refused snapshot exited 0"
case $OUT in *REFUSED-BY-HOOK*) ok "refused snapshot shows git's stderr" ;; *) bad "snapshot refusal stderr hidden: $OUT" ;; esac
case $OUT in *"no upstream changes."*) bad "refused snapshot printed 'no upstream changes.'" ;; *) ok "refused snapshot never says 'no upstream changes.'" ;; esac

# 2. refused upstream commit (clean snapshot, npx changes the tree)
d=$(fixture refuse-upstream); refuse_hook "$d"
run "$d" change
[ "$RC" -ne 0 ] && ok "refused upstream commit exits non-zero" || bad "refused upstream commit exited 0"
case $OUT in *REFUSED-BY-HOOK*) ok "refused upstream commit shows git's stderr" ;; *) bad "upstream refusal stderr hidden: $OUT" ;; esac
case $OUT in *"no upstream changes."*) bad "refused upstream printed 'no upstream changes.'" ;; *) ok "refused upstream never says 'no upstream changes.'" ;; esac

# 3. the genuine nothing-to-commit case still exits 0 with its message
d=$(fixture nothing)
run "$d" none
check "nothing to commit exits 0" 0 "$RC"
case $OUT in *"no upstream changes."*) ok "nothing to commit says so" ;; *) bad "missing 'no upstream changes.': $OUT" ;; esac

# 4. the script no longer overrides the identity: a commit carries the checkout's
d=$(fixture identity); echo edit > "$d/a/SKILL.md"
run "$d" none
check "snapshot author is the checkout's identity" "t@example.com" "$(git -C "$d" log -1 --format=%ae)"

[ "$fails" -eq 0 ] || { echo "$fails failure(s)"; exit 1; }
