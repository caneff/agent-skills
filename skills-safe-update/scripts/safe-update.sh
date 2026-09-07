#!/usr/bin/env bash
# Safe wrapper around `npx skills update`: a git buffer makes every update
# reviewable and reversible, and skills you have edited are three-way merged
# with upstream instead of being silently overwritten (or silently frozen).
# Hand-installed skills registered in .extra-skills.json (name -> {repo, path,
# treeSha}) are synced from their github upstreams in the same run.
# Sourceable: defining the helpers runs nothing, so tests can call them.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS="${SKILLS_DIR:-$HOME/.agents/skills}"
git(){ command git -c user.email=skills@local -c user.name=skills "$@"; }

# ---------------------------------------------------------- three-way merge

# resolve_base_tree <tree-sha> — print the merge base, or fail.
# The base is the upstream version you HAD installed. The lock's
# skillFolderHash IS that folder's git tree SHA, so it addresses the base
# directly; there is nothing to search for, because the object is in the
# buffer's database exactly when some commit held that version. It is missing
# only for a skill the buffer never saw clean (a manual .protected-skills
# entry, or a lock hash pruned as unreachable) — the caller falls back there.
resolve_base_tree(){
  local hash=${1:-}
  [ -n "$hash" ] || return 1
  git rev-parse -q --verify "$hash^{tree}" 2>/dev/null
}

# oid <tree-ish>:<path> — blob SHA, or empty when the path is absent.
oid(){ git rev-parse -q --verify "$1" 2>/dev/null || true; }

# put <tree-ish> <path-in-tree> <dest> — write that blob out, mode included.
put(){
  local mode
  mode=$(git ls-tree "$1" -- "$2" | awk '{print $1}')
  mkdir -p "$(dirname "$3")"
  git cat-file blob "$1:$2" > "$3"
  case "$mode" in *755) chmod +x "$3" ;; *) chmod -x "$3" ;; esac
}

# merge_skill <skill> <base-tree> <pre> <post>
# Three-way merge one protected skill into the working tree, which holds
# <post> on entry: base = the upstream version you installed, yours = <pre>,
# theirs = <post>. Prints one "<STATUS>\t<path>" line per file that needed a
# decision (MERGED / CONFLICT / LOCAL / UPSTREAM); returns 1 if any file
# conflicted, else 0. Conflicts are left in the file as markers, not dropped.
merge_skill(){
  local skill=$1 base=$2 pre=$3 post=$4
  local conflicted=0 f bo lo uo rc st tmp
  tmp=$(mktemp -d)
  local files
  files=$( { git ls-tree -r --name-only "$base"        2>/dev/null || true
             git ls-tree -r --name-only "$pre:$skill"  2>/dev/null || true
             git ls-tree -r --name-only "$post:$skill" 2>/dev/null || true
           } | sort -u )
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    bo=$(oid "$base:$f"); lo=$(oid "$pre:$skill/$f"); uo=$(oid "$post:$skill/$f")
    [ "$lo" = "$uo" ] && continue                  # nothing to decide
    st=
    if [ -z "$lo" ]; then                          # absent from your version
      if   [ -z "$bo" ];      then st=UPSTREAM     # brand-new upstream file
      elif [ "$bo" = "$uo" ]; then st=LOCAL; rm -f "$skill/$f"   # you deleted it
      else st=CONFLICT; conflicted=1               # you deleted, upstream changed
      fi
    elif [ -z "$uo" ]; then                        # absent from upstream
      if   [ -z "$bo" ];      then st=LOCAL;    put "$pre" "$skill/$f" "$skill/$f"
      elif [ "$bo" = "$lo" ]; then st=UPSTREAM  # upstream deleted, you hadn't edited
      else st=CONFLICT; conflicted=1; put "$pre" "$skill/$f" "$skill/$f"
      fi
    elif [ "$lo" = "$bo" ]; then st=UPSTREAM       # you never touched it
    elif [ "$uo" = "$bo" ]; then st=LOCAL; put "$pre" "$skill/$f" "$skill/$f"
    else
      put "$pre" "$skill/$f" "$tmp/ours"
      put "$base" "$f" "$tmp/base"
      put "$post" "$skill/$f" "$tmp/theirs"
      rc=0
      git merge-file -q -L "yours: $skill/$f" -L "installed upstream" \
        -L "new upstream" "$tmp/ours" "$tmp/base" "$tmp/theirs" || rc=$?
      if [ "$rc" -eq 0 ]; then
        st=MERGED
        put "$post" "$skill/$f" "$skill/$f"; cat "$tmp/ours" > "$skill/$f"
      elif [ "$rc" -lt 128 ]; then                 # rc = number of conflicts
        st=CONFLICT; conflicted=1
        put "$post" "$skill/$f" "$skill/$f"; cat "$tmp/ours" > "$skill/$f"
      else                                         # unmergeable (binary): keep yours
        st=CONFLICT; conflicted=1; put "$pre" "$skill/$f" "$skill/$f"
      fi
    fi
    printf '%s\t%s\n' "$st" "$f"
  done <<< "$files"
  rm -rf "$tmp"
  return "$conflicted"
}

# ------------------------------------------------------------------- update

main(){
cd "$SKILLS"

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
# upstream version — which is exactly the base of the three-way merge below.
# Read it AFTER npx (as we used to) and npx has already rewritten it to the
# NEW upstream — making every updated skill look edited, and destroying the
# only pointer to the base. hand-installed skills (.extra-skills.json) join
# the same map: treeSha is their installed-upstream hash, same semantics.
EXTRA="$SKILLS/.extra-skills.json"
PRELOCK=$(mktemp)
python3 "$SCRIPT_DIR/upstream.py" prelock --lock "$LOCK" --extras "$EXTRA" > "$PRELOCK"

echo "running: npx skills update -g"
npx -y skills update -g

# 3b. sync hand-installed skills straight from their github upstreams.
# Runs before the POST commit, so the PRE/POST buffer, protection, and digest
# cover them exactly like lockfile skills.
if [ -f "$EXTRA" ]; then
  echo "syncing extra skills (.extra-skills.json)"
  python3 "$SCRIPT_DIR/upstream.py" sync-extras --extras "$EXTRA"
fi

# 4. record upstream result (npx rewrote the live lock — mirror the new one in)
snap_lock
git add -A
if ! git commit -qm "upstream: skills update $(date +%F)" >/dev/null 2>&1; then
  echo "no upstream changes."; exit 0
fi
POST=$(git rev-parse HEAD)

# 5. protect locally-edited skills: merge YOUR version with upstream's.
# Protected set = AUTO-DETECTED (pre-update on-disk tree diverged from the
# PRE-UPDATE lock hash, i.e. from the upstream version you had installed)
# UNION any manual entries in .protected-skills (override for untracked/edge cases).
declare -A PROT BASEHASH
if [ -s "$PRELOCK" ]; then
  while IFS=$'\t' read -r name hash; do
    [ -z "$name" ] && continue
    cur=$(git rev-parse "$PRE:$name" 2>/dev/null) || continue   # tree SHA of your pre-update version
    BASEHASH[$name]=$hash
    [ "$cur" != "$hash" ] && PROT[$name]=1                       # diverged from installed upstream => you edited it
  done < "$PRELOCK"
fi
rm -f "$PRELOCK"
if [ -f .protected-skills ]; then
  while read -r s; do [[ -z "$s" || "$s" == \#* ]] && continue; PROT[$s]=1; done < .protected-skills
fi

merged=(); conflicted=(); nobase=(); report=""
for s in "${!PROT[@]}"; do
  [ -e "$s" ] || continue
  if git diff --quiet "$PRE" "$POST" -- "$s"; then continue; fi   # upstream left it alone
  if base=$(resolve_base_tree "${BASEHASH[$s]:-}"); then
    rc=0; out=$(merge_skill "$s" "$base" "$PRE" "$POST") || rc=$?
    if [ "$rc" -eq 0 ]; then merged+=("$s"); else conflicted+=("$s"); fi
    report+="$s  (base ${base:0:9})"$'\n'
    report+=$(printf '%s\n' "$out" | awk -F'\t' 'NF==2{printf "  %-9s %s\n", $1, $2}')$'\n'
  else
    # No base to merge from — never guess one. Keep YOUR version whole-file and
    # say so; the upstream delta stays one `git diff PRE POST` away.
    git checkout "$PRE" -- "$s"; nobase+=("$s")
  fi
done
if [ -n "$report" ] || [ ${#nobase[@]} -gt 0 ]; then
  git add -A && git commit -qm "merge local edits with upstream (three-way)" >/dev/null 2>&1 || true
fi

# Categorize every skill that changed upstream (PRE..POST). Protected ones are
# reported by name below, so exclude them from the plain "updated" list.
changed=$(git --no-pager diff --name-only "$PRE" "$POST" | cut -d/ -f1 | sort -u | grep -vE '^\.(skill-lock|extra-skills)\.json$' || true)
declare -A PROTECTED_SET
for s in "${merged[@]:-}" "${conflicted[@]:-}" "${nobase[@]:-}"; do [ -n "$s" ] && PROTECTED_SET[$s]=1; done

echo
echo "=== update summary ==="
updated=()
for s in $changed; do
  [ -n "${PROTECTED_SET[$s]:-}" ] || updated+=("$s")
done
echo "Updated from upstream (${#updated[@]}):"
for s in "${updated[@]:-}"; do [ -n "$s" ] && echo "  $s"; done
if [ ${#merged[@]} -gt 0 ]; then
  echo "Your edits merged with upstream (${#merged[@]}): ${merged[*]}"
fi
if [ ${#conflicted[@]} -gt 0 ]; then
  echo "CONFLICTED — files below carry conflict markers, resolve them (${#conflicted[@]}): ${conflicted[*]}"
fi
if [ ${#nobase[@]} -gt 0 ]; then
  echo "No merge base — your version kept whole-file, upstream delta NOT applied (${#nobase[@]}):"
  for s in "${nobase[@]}"; do echo "  $s   (review: git -C $SKILLS diff $PRE $POST -- $s)"; done
fi

if [ -n "$report" ]; then
  echo
  echo "=== protected skills: three-way merge (yours vs installed upstream vs new upstream) ==="
  printf '%s' "$report"
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
echo "DIGEST_MERGED=${merged[*]:-}"
echo "DIGEST_CONFLICTED=${conflicted[*]:-}"
echo "DIGEST_KEPT=${nobase[*]:-}"
echo
echo "undo everything:  git -C $SKILLS reset --hard $PRE"

# A conflict needs a human before these skills are usable — say so in the exit code.
[ ${#conflicted[@]} -eq 0 ] || exit 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
