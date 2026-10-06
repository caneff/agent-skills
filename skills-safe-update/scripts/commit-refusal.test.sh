#!/usr/bin/env bash
# Runs safe-update.sh's main() end to end against a fixture buffer with a fake
# `npx`, to prove a refused commit is never read as "nothing to commit"
# (#1450). The script used to force `-c user.email=skills@local`, which the
# checkout's commit-identity guard refuses; it then swallowed the refusal
# twice (the snapshot commit ended in `|| true`, the upstream commit's failure
# printed "no upstream changes." and exited 0).
# No network. Every repo, TMPDIR and HOME is under $WORK, and this repo's HEAD
# and status are asserted unchanged at the end (the protect.test.sh tripwire).
set -uo pipefail
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/safe-update.sh"
here="$(dirname "$SCRIPT")"
. "$here/../../tests/fixture-identity.sh"
REPO=$(command git -C "$here" rev-parse --show-toplevel)
HEAD_BEFORE=$(command git -C "$REPO" rev-parse HEAD)
STATUS_BEFORE=$(command git -C "$REPO" status --porcelain)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
# An empty home and TMPDIR: no global git config or hooks path leaks in, and
# the script's mktemp files land where the trap above removes them.
mkdir -p "$WORK/home" "$WORK/tmp"
export HOME="$WORK/home" TMPDIR="$WORK/tmp" GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1

fails=0
ok(){ printf 'ok   %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi; }
has(){ case $2 in *"$3"*) ok "$1" ;; *) bad "$1 — missing [$3] in: $2" ;; esac; }
lacks(){ case $2 in *"$3"*) bad "$1 — found [$3] in: $2" ;; *) ok "$1" ;; esac; }

# fake npx: what `npx skills update -g` does to the tree, per case by
# $FAKE_NPX (change = rewrite a skill file). It leaves a marker when it runs.
mkdir -p "$WORK/bin"
cat > "$WORK/bin/npx" <<'EOF'
#!/usr/bin/env bash
: > "$SKILLS_DIR/../npx-ran"
[ "${FAKE_NPX:-none}" = change ] && echo upstream > "$SKILLS_DIR/a/SKILL.md"
exit 0
EOF
chmod +x "$WORK/bin/npx"

# fixture <name> — a committed buffer (lock included, so the snapshot is clean
# unless a case edits something) with identity "t <t@example.com>".
fixture(){
  local d="$WORK/$1/skills"
  mkdir -p "$d/a"; echo base > "$d/a/SKILL.md"
  echo '{"version":3,"skills":{}}' | tee "$WORK/$1/.skill-lock.json" > "$d/.skill-lock.json"
  git -C "$d" init -q . && fixture_identity "$d" "$WORK" || return 1
  git -C "$d" add -A && git -C "$d" commit -qm base || return 1
  echo "$d"
}
# hook <dir> <name> — refuse commits at <name> (pre-commit: all of them;
# commit-msg: only a message that contains "three-way").
hook(){
  local body='echo "REFUSED-BY-HOOK" >&2; exit 1'
  [ "$2" = commit-msg ] && body='grep -q three-way "$1" && { echo "REFUSED-BY-HOOK" >&2; exit 1; }; exit 0'
  printf '#!/bin/sh\n%s\n' "$body" > "$1/.git/hooks/$2"; chmod +x "$1/.git/hooks/$2"
}
run(){ # run <skills-dir> <FAKE_NPX> — sets OUT, RC
  case $1 in "$WORK"/*) ;; *) bad "run: '$1' is not a fixture under \$WORK"; OUT=; RC=99; return 1 ;; esac
  rm -f "$1/../npx-ran"
  OUT=$(SKILLS_DIR=$1 SKILL_LOCK=$1/../.skill-lock.json FAKE_NPX=$2 \
        PATH="$WORK/bin:$PATH" bash "$SCRIPT" 2>&1); RC=$?
}
nonzero(){ [ "$RC" -ne 0 ] && ok "$1" || bad "$1 — exited 0: $OUT"; }

# 1. refused snapshot commit (local edit pending): non-zero, stderr shown, and
#    npx never ran (a snapshot refusal must stop before the update)
d=$(fixture refuse-snapshot); hook "$d" pre-commit; echo edit > "$d/a/SKILL.md"
run "$d" change
nonzero "refused snapshot commit exits non-zero"
has "refused snapshot shows git's stderr" "$OUT" REFUSED-BY-HOOK
has "refused snapshot says the snapshot failed" "$OUT" "pre-update snapshot failed"
lacks "refused snapshot never says 'no upstream changes.'" "$OUT" "no upstream changes."
[ ! -e "$d/../npx-ran" ] && ok "refused snapshot stops before npx runs" || bad "npx ran after a refused snapshot"

# 2. refused upstream commit (snapshot clean, npx changes the tree)
d=$(fixture refuse-upstream); hook "$d" pre-commit
run "$d" change
nonzero "refused upstream commit exits non-zero"
has "refused upstream shows git's stderr" "$OUT" REFUSED-BY-HOOK
has "refused upstream says the upstream commit failed" "$OUT" "upstream commit failed"
lacks "refused upstream never says 'no upstream changes.'" "$OUT" "no upstream changes."
[ -e "$d/../npx-ran" ] && ok "upstream case reached npx" || bad "upstream case never reached npx"

# 3. refused three-way merge commit (a .protected-skills entry forces the
#    keep-yours path, which stages a change and commits it)
d=$(fixture refuse-merge); echo a > "$d/.protected-skills"
git -C "$d" add -A; git -C "$d" commit -qm protect; hook "$d" commit-msg
echo edit > "$d/a/SKILL.md"
run "$d" change
nonzero "refused merge commit exits non-zero"
has "refused merge commit shows git's stderr" "$OUT" REFUSED-BY-HOOK
has "refused merge commit says so" "$OUT" "merge commit failed"
lacks "refused merge commit prints no summary" "$OUT" "update summary"

# 4. the genuine nothing-to-commit case still exits 0 with its message
d=$(fixture nothing)
run "$d" none
check "nothing to commit exits 0" 0 "$RC"
has "nothing to commit says so" "$OUT" "no upstream changes."

# 5. the script no longer overrides the identity: commits carry the checkout's
d=$(fixture identity); echo edit > "$d/a/SKILL.md"
run "$d" none
check "snapshot author is the checkout's identity" t@example.com "$(git -C "$d" log -1 --format=%ae)"

# 6. a buffer whose baseline commit never happened (unborn HEAD) recovers: the
#    snapshot makes the root commit instead of failing on `diff HEAD`
d="$WORK/unborn/skills"; mkdir -p "$d/a"; echo base > "$d/a/SKILL.md"
echo '{"version":3,"skills":{}}' | tee "$WORK/unborn/.skill-lock.json" > /dev/null
git -C "$d" init -q . && fixture_identity "$d" "$WORK"
run "$d" none
check "unborn HEAD recovers with a root commit" 0 "$RC"
check "unborn HEAD now has a commit" 1 "$(git -C "$d" rev-list --count HEAD 2>/dev/null)"

# tripwire: nothing above may have touched this repo
check "repo HEAD unchanged" "$HEAD_BEFORE" "$(command git -C "$REPO" rev-parse HEAD)"
check "repo status unchanged" "$STATUS_BEFORE" "$(command git -C "$REPO" status --porcelain)"
check "no mktemp file leaked outside TMPDIR cleanup" 0 "$(ls "$WORK/tmp" | wc -l)"

[ "$fails" -eq 0 ] || { echo "$fails failure(s)"; exit 1; }
