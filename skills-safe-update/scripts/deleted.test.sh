#!/usr/bin/env bash
# A lock-tracked skill whose folder you deleted on purpose must stay deleted
# after safe-update.sh (#2023): npx reinstalls the folder and re-links
# ~/.claude/skills/<name>, and the run must undo both and say so. A fake `npx`
# on PATH stands in for the real one; no network.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
. "$SCRIPT_DIR/../../tests/fixture-identity.sh"
fixture_env

fails=0
ok(){ printf 'ok   %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi; }

export SKILLS_DIR="$WORK/skills" SKILL_LOCK="$WORK/.skill-lock.json" CLAUDE_SKILLS_DIR="$WORK/claude-skills"
mkdir -p "$SKILLS_DIR/keepme" "$SKILLS_DIR/gone" "$CLAUDE_SKILLS_DIR" "$WORK/bin"
echo v1 > "$SKILLS_DIR/keepme/SKILL.md"; echo v1 > "$SKILLS_DIR/gone/SKILL.md"
ln -s "$SKILLS_DIR/keepme" "$CLAUDE_SKILLS_DIR/keepme"
git -C "$SKILLS_DIR" init -q .; git -C "$SKILLS_DIR" add -A; git -C "$SKILLS_DIR" commit -qm skills
# skillFolderHash is the installed folder's tree sha, so keepme reads unedited
h1=$(git -C "$SKILLS_DIR" rev-parse HEAD:keepme); h2=$(git -C "$SKILLS_DIR" rev-parse HEAD:gone)
printf '{"skills":{"keepme":{"sourceUrl":"https://github.com/a/b","skillPath":"keepme/SKILL.md","skillFolderHash":"%s"},"gone":{"sourceUrl":"https://github.com/a/b","skillPath":"gone/SKILL.md","skillFolderHash":"%s"}}}\n' "$h1" "$h2" > "$SKILL_LOCK"
cp "$SKILL_LOCK" "$SKILLS_DIR/.skill-lock.json" \
  && git -C "$SKILLS_DIR" add -A && git -C "$SKILLS_DIR" commit -qm base

# you delete it on purpose
rm -rf "$SKILLS_DIR/gone"

# the fake npx: updates keepme, and reinstalls + re-links the deleted skill
cat > "$WORK/bin/npx" <<'NPX'
#!/usr/bin/env bash
echo v2 > "$SKILLS_DIR/keepme/SKILL.md"
mkdir -p "$SKILLS_DIR/gone/reference"; echo upstream > "$SKILLS_DIR/gone/SKILL.md"; echo r > "$SKILLS_DIR/gone/reference/x.md"
ln -sfn "$SKILLS_DIR/gone" "$CLAUDE_SKILLS_DIR/gone"
exit 0
NPX
chmod +x "$WORK/bin/npx"

out=$(PATH="$WORK/bin:$PATH" bash "$SCRIPT_DIR/safe-update.sh" 2>&1); rc=$?
check "the run succeeds" 0 "$rc"; [ -n "${SHOW:-}" ] && echo "$out"
if [ -e "$SKILLS_DIR/gone" ]; then bad "the deleted skill's folder stays deleted"; else ok "the deleted skill's folder stays deleted"; fi
if [ -L "$CLAUDE_SKILLS_DIR/gone" ] || [ -e "$CLAUDE_SKILLS_DIR/gone" ]; then bad "its ~/.claude/skills link is removed"; else ok "its ~/.claude/skills link is removed"; fi
check "another skill still updates" v2 "$(cat "$SKILLS_DIR/keepme/SKILL.md")"
[ -L "$CLAUDE_SKILLS_DIR/keepme" ] && ok "another skill's link is untouched" || bad "another skill's link is untouched"
if git -C "$SKILLS_DIR" ls-tree -r --name-only HEAD | grep -q '^gone/'; then bad "the update commit holds no resurrected file"; else ok "the update commit holds no resurrected file"; fi
updated_block=$(printf '%s\n' "$out" | awk '/^Updated from upstream/{f=1;next} f&&/^  /{print;next} {f=0}')
if printf '%s\n' "$updated_block" | grep -qw gone; then bad "it is not reported as Updated from upstream"; else ok "it is not reported as Updated from upstream"; fi
printf '%s\n' "$updated_block" | grep -qw keepme && ok "the real update is reported" || bad "the real update is reported"
printf '%s\n' "$out" | grep -q '^Kept deleted (1): gone' && ok "the summary names it as kept deleted" || bad "the summary names it as kept deleted"
printf '%s\n' "$out" | grep -q '^DIGEST_DELETED=gone$' && ok "the digest anchor names it" || bad "the digest anchor names it"
check "the buffer tree is clean" "" "$(git -C "$SKILLS_DIR" status --porcelain)"

[ "$fails" -eq 0 ] || { echo "$fails failure(s)"; exit 1; }
echo "all deleted-skill tests passed"
