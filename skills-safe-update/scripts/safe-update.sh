#!/usr/bin/env bash
# Safe wrapper around `npx skills update`: a git buffer makes every update
# reviewable and reversible, and skills listed in .protected-skills keep their
# local edits instead of being silently overwritten.
# Hand-installed skills registered in .extra-skills.json (name -> {repo, path,
# treeSha}) are synced from their github upstreams in the same run.
set -euo pipefail
SKILLS="${SKILLS_DIR:-$HOME/.agents/skills}"
cd "$SKILLS"
git(){ command git -c user.email=skills@local -c user.name=skills "$@"; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  git init -q && git add -A && git commit -qm "baseline: skills as of $(date +%F)"
  echo "initialized git buffer in $SKILLS"
fi

# the live lock sits OUTSIDE this repo (npx writes it to the skills-dir parent),
# so it isn't backed up by git on its own. Mirror it into the repo at each
# snapshot — PRE holds the old lock, POST the new — so the remote fully
# reconstructs a run. Kept as a plain tracked copy (not a symlink: npx's
# atomic-rename writes would clobber a symlink with a regular file silently).
LOCK="${SKILL_LOCK:-$(dirname "$SKILLS")/.skill-lock.json}"
snap_lock(){ [ -f "$LOCK" ] && cp "$LOCK" "$SKILLS/.skill-lock.json"; }

# 2. snapshot current state (so PRE holds your edits)
snap_lock
git add -A
git commit -qm "pre-update snapshot $(date +%F)" >/dev/null 2>&1 || true
PRE=$(git rev-parse HEAD)

# capture the lock's upstream hashes BEFORE updating. skillFolderHash IS the
# git tree SHA of the skill folder, so a hash here describes the *installed*
# upstream version. Read it AFTER npx (as we used to) and npx has already
# rewritten it to the NEW upstream — making every updated skill look edited.
PRELOCK=$(mktemp)
[ -f "$LOCK" ] && python3 -c "import json;d=json.load(open('$LOCK')).get('skills',{});[print(k+chr(9)+v.get('skillFolderHash','')) for k,v in d.items()]" > "$PRELOCK"
# hand-installed skills (.extra-skills.json) join the same protection map:
# treeSha is their installed-upstream hash, same semantics as skillFolderHash.
EXTRA="$SKILLS/.extra-skills.json"
[ -f "$EXTRA" ] && python3 -c "import json;d=json.load(open('$EXTRA'));[print(k+chr(9)+v.get('treeSha','')) for k,v in d.items()]" >> "$PRELOCK"

echo "running: npx skills update -g"
npx -y skills update -g

# 3b. sync hand-installed skills straight from their github upstreams.
# Runs before the POST commit, so the PRE/POST buffer, protection, and digest
# cover them exactly like lockfile skills.
if [ -f "$EXTRA" ]; then
  echo "syncing extra skills (.extra-skills.json)"
  python3 - "$EXTRA" <<'PY'
import io, json, os, shutil, subprocess, sys, tarfile

manifest_path = sys.argv[1]
manifest = json.load(open(manifest_path))

def sh(*a):
    return subprocess.run(a, capture_output=True)

for name, e in manifest.items():
    repo, path = e["repo"], e.get("path", "")
    r = sh("gh", "api", f"repos/{repo}/commits/HEAD", "--jq", ".sha+\" \"+.commit.tree.sha")
    if r.returncode != 0:
        print(f"  {name}: upstream fetch failed, skipped"); continue
    head, root_tree = r.stdout.decode().split()
    if path:
        r = sh("gh", "api", f"repos/{repo}/git/trees/{head}?recursive=1")
        if r.returncode != 0:
            print(f"  {name}: tree fetch failed, skipped"); continue
        trees = {t["path"]: t["sha"] for t in json.loads(r.stdout).get("tree", []) if t["type"] == "tree"}
        up = trees.get(path)
    else:
        up = root_tree
    if not up:
        print(f"  {name}: path {path!r} gone upstream (ORPHAN), skipped"); continue
    if up == e.get("treeSha"):
        continue
    r = sh("gh", "api", f"repos/{repo}/tarball/{head}")
    if r.returncode != 0:
        print(f"  {name}: tarball fetch failed, skipped"); continue
    tf = tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:gz")
    prefix = tf.getmembers()[0].name.split("/")[0]
    want = f"{prefix}/{path}".rstrip("/") + "/"
    if os.path.isdir(name):
        shutil.rmtree(name)  # reversible: PRE snapshot holds the old version
    for mem in tf.getmembers():
        if not mem.isfile() or not mem.name.startswith(want) or ".." in mem.name:
            continue
        dest = os.path.join(name, mem.name[len(want):])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(tf.extractfile(mem).read())
    e["treeSha"] = up
    print(f"  {name}: synced from {repo}@{head[:9]}")

with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY
fi

# 4. record upstream result (npx rewrote the live lock — mirror the new one in)
snap_lock
git add -A
if ! git commit -qm "upstream: skills update $(date +%F)" >/dev/null 2>&1; then
  echo "no upstream changes."; exit 0
fi
POST=$(git rev-parse HEAD)

# 5. protect locally-edited skills: keep YOUR version, flag upstream delta.
# Protected set = AUTO-DETECTED (pre-update on-disk tree diverged from the
# PRE-UPDATE lock hash, i.e. from the upstream version you had installed)
# UNION any manual entries in .protected-skills (override for untracked/edge cases).
declare -A PROT
if [ -s "$PRELOCK" ]; then
  while IFS=$'\t' read -r name hash; do
    [ -z "$name" ] && continue
    cur=$(git rev-parse "$PRE:$name" 2>/dev/null) || continue   # tree SHA of your pre-update version
    [ "$cur" != "$hash" ] && PROT[$name]=1                       # diverged from installed upstream => you edited it
  done < "$PRELOCK"
fi
rm -f "$PRELOCK"
if [ -f .protected-skills ]; then
  while read -r s; do [[ -z "$s" || "$s" == \#* ]] && continue; PROT[$s]=1; done < .protected-skills
fi

restored=()
for s in "${!PROT[@]}"; do
  if [ -e "$s" ] && ! git diff --quiet "$PRE" "$POST" -- "$s"; then
    git checkout "$PRE" -- "$s"; restored+=("$s")
  fi
done
if [ ${#restored[@]} -gt 0 ]; then
  git add -A && git commit -qm "restore local edits to protected skills"
  echo
  echo "Protected skills changed upstream — your edits were KEPT. Review the upstream delta and merge by hand if wanted:"
  for s in "${restored[@]}"; do echo "  git -C $SKILLS diff $PRE $POST -- $s"; done
fi

# Categorize every skill that changed upstream (PRE..POST). Restored ones net to
# zero across PRE..HEAD, so they'd vanish from a PRE..HEAD stat — compute against
# POST and label them explicitly instead.
changed=$(git --no-pager diff --name-only "$PRE" "$POST" | cut -d/ -f1 | sort -u | grep -vE '^\.(skill-lock|extra-skills)\.json$' || true)
declare -A RESTORED_SET
for s in "${restored[@]:-}"; do [ -n "$s" ] && RESTORED_SET[$s]=1; done

echo
echo "=== update summary ==="
updated=(); kept=()
for s in $changed; do
  if [ -n "${RESTORED_SET[$s]:-}" ]; then kept+=("$s"); else updated+=("$s"); fi
done
echo "Updated from upstream (${#updated[@]}):"
for s in "${updated[@]:-}"; do [ -n "$s" ] && echo "  $s"; done
if [ ${#kept[@]} -gt 0 ]; then
  echo "Kept your local edits — upstream delta NOT applied (${#kept[@]}):"
  for s in "${kept[@]}"; do echo "  $s   (review: git -C $SKILLS diff $PRE $POST -- $s)"; done
fi

echo
echo "=== per-skill changes (upstream, PRE..POST) ==="
git --no-pager diff --stat "$PRE" "$POST" -- $changed

# Machine-readable anchors for the digest step (SKILL.md reads these to write the
# plain-English summary). Keep the exact key names — the skill greps for them.
echo
echo "DIGEST_PRE=$PRE"
echo "DIGEST_POST=$POST"
echo "DIGEST_SKILLS_DIR=$SKILLS"
echo "DIGEST_CHANGED=$(echo $changed | tr '\n' ' ')"
echo "DIGEST_KEPT=${kept[*]:-}"
echo
echo "undo everything:  git -C $SKILLS reset --hard $PRE"
