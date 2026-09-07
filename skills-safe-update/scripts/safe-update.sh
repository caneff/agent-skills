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
# The base is the upstream version you HAD installed, and the lock's
# skillFolderHash IS that folder's git tree SHA, so it addresses the base
# directly — no history to walk, since the object is in the buffer's database
# exactly when some commit held that version.
resolve_base_tree(){
  local hash=${1:-}
  [ -n "$hash" ] || return 1
  git rev-parse -q --verify "$hash^{tree}" 2>/dev/null
}

# oid <tree-ish>:<path> — blob SHA, or empty when the path is absent.
oid(){ git rev-parse -q --verify "$1" 2>/dev/null || true; }

# entry_mode <tree-ish> <path-in-tree> — the 6-digit mode git records for it.
entry_mode(){ git ls-tree "$1" -- "$2" | awk '{print $1}'; }

# put <tree-ish> <path-in-tree> <dest> — write that blob out, mode included.
# The rm is load-bearing: writing through an existing symlink would follow it
# and dump the content wherever it points, leaving the link itself untouched.
# Every step reports its own failure: `set -e` is suppressed inside merge_skill
# (main tests its status), so a silent write failure would otherwise be reported
# as a merge result.
put(){
  local mode; mode=$(entry_mode "$1" "$2") || return 1
  mkdir -p "$(dirname "$3")" || return 1
  rm -f "$3" || return 1
  if [ "$mode" = 120000 ]; then ln -s "$(git cat-file blob "$1:$2")" "$3" || return 1; return 0; fi
  git cat-file blob "$1:$2" > "$3" || return 1
  case "$mode" in *755) chmod +x "$3" ;; *) chmod -x "$3" ;; esac
}

# install_merged <mode-tree> <path> <merged-file> — put the merged text at
# <path> with the mode <mode-tree> records, by writing that blob for its mode
# and then overwriting the bytes.
install_merged(){ put "$1" "$2" "$2" || return 1; cat "$3" > "$2"; }

# merge_skill <skill> <base-tree> <pre> <post>
# Three-way merge one protected skill into the working tree, which holds
# <post> on entry: base = the upstream version you installed, yours = <pre>,
# theirs = <post>. Prints one "<STATUS>\t<path>" line per file that needed a
# decision (MERGED / CONFLICT / LOCAL / UPSTREAM); exits 1 if any file
# conflicted, 0 if none, and >1 if the merge itself failed (the caller must
# not read that as a clean run). Text conflicts are left in the file as
# markers, not dropped. Runs as a subshell so its scratch dir is cleaned even
# when `set -e` aborts it mid-merge.
merge_skill(){ (
  local skill=$1 base=$2 pre=$3 post=$4
  local conflicted=0 f bo lo uo rc st tmp note mode_src bm pm
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  # -z: --name-only alone honours core.quotePath, which mangles a non-ASCII
  # name into an escaped string that matches nothing — the file would then be
  # skipped in silence, taking your edits with it.
  # NUL-separated straight into the loop: a command substitution would drop
  # the separators, and a variable cannot hold them.
  while IFS= read -r -d '' f; do
    [ -n "$f" ] || continue
    bo=$(oid "$base:$f"); lo=$(oid "$pre:$skill/$f"); uo=$(oid "$post:$skill/$f")
    note=
    if [ "$lo" = "$uo" ]; then                     # same bytes on both sides...
      # ...but a mode YOU changed is a local edit like any other. Upstream
      # changing the mode while you left it alone needs nothing: the working
      # tree already holds POST.
      if [ -n "$lo" ] \
         && [ "$(entry_mode "$pre" "$skill/$f")" != "$(entry_mode "$post" "$skill/$f")" ] \
         && [ "$(entry_mode "$pre" "$skill/$f")" != "$(entry_mode "$base" "$f")" ]; then
        put "$pre" "$skill/$f" "$skill/$f" || exit 2
        printf '%s\t%s\t%s\n' LOCAL "$f" "your file mode kept"
      fi
      continue
    fi
    st=
    if [ -z "$lo" ]; then                          # absent from your version
      if   [ -z "$bo" ];      then st=UPSTREAM     # brand-new upstream file
      elif [ "$bo" = "$uo" ]; then st=LOCAL; rm -f "$skill/$f" || exit 2   # you deleted it
      else                                         # you deleted, upstream changed
        st=CONFLICT; conflicted=1
        note="you deleted this file; upstream changed it, and ITS version is in the tree"
      fi
    elif [ -z "$uo" ]; then                        # absent from upstream
      if   [ -z "$bo" ];      then st=LOCAL;    put "$pre" "$skill/$f" "$skill/$f" || exit 2
      elif [ "$bo" = "$lo" ]; then st=UPSTREAM  # upstream deleted, you hadn't edited
      else
        st=CONFLICT; conflicted=1; put "$pre" "$skill/$f" "$skill/$f" || exit 2
        note="upstream deleted this file; you had edited it, and YOUR version is in the tree"
      fi
    elif [ "$lo" = "$bo" ]; then st=UPSTREAM       # you never touched it
    elif [ "$uo" = "$bo" ]; then st=LOCAL; put "$pre" "$skill/$f" "$skill/$f" || exit 2
    elif [ "$(entry_mode "$pre" "$skill/$f")" = 120000 ] \
      || [ "$(entry_mode "$post" "$skill/$f")" = 120000 ]; then
      # a symlink has no lines to merge — keep yours and say so, rather than
      # writing upstream's target string into a regular file.
      st=CONFLICT; conflicted=1; put "$pre" "$skill/$f" "$skill/$f" || exit 2
      note="symlink — not line-mergeable; YOUR version is in the tree"
    else
      put "$pre" "$skill/$f" "$tmp/ours" || exit 2
      # An empty base covers both sides ADDING the file (base has no such path)
      # and a base that recorded a SYMLINK where both sides now hold regular
      # files — putting that back would make merge-file read through the link
      # and merge against whatever it points at.
      bm=$(entry_mode "$base" "$f")
      if [ -n "$bo" ] && [ "$bm" != 120000 ]; then
        put "$base" "$f" "$tmp/base" || exit 2
      else
        : > "$tmp/base"; bm=
      fi
      put "$post" "$skill/$f" "$tmp/theirs" || exit 2
      # A mode you changed yourself is a local edit like any other: keep it.
      # With no usable base, upstream had nothing to change the mode from, so
      # any divergence between the two sides is yours.
      pm=$(entry_mode "$pre" "$skill/$f"); mode_src=$post
      if [ -n "$bm" ]; then
        if [ "$pm" != "$bm" ]; then mode_src=$pre; fi
      elif [ "$pm" != "$(entry_mode "$post" "$skill/$f")" ]; then
        mode_src=$pre
      fi
      rc=0
      git merge-file -q -L "yours: $skill/$f" -L "installed upstream" \
        -L "new upstream" "$tmp/ours" "$tmp/base" "$tmp/theirs" || rc=$?
      if [ "$rc" -eq 0 ]; then
        st=MERGED; install_merged "$mode_src" "$skill/$f" "$tmp/ours" || exit 2
      elif [ "$rc" -lt 128 ]; then                 # rc = number of conflicts
        st=CONFLICT; conflicted=1
        install_merged "$mode_src" "$skill/$f" "$tmp/ours" || exit 2
      else                                         # unmergeable (binary): keep yours
        st=CONFLICT; conflicted=1; put "$pre" "$skill/$f" "$skill/$f" || exit 2
        note="not line-mergeable (binary?); YOUR version is in the tree"
      fi
    fi
    printf '%s\t%s\t%s\n' "$st" "$f" "$note"
  done < <( { git ls-tree -rz --name-only "$base"        2>/dev/null || true
              git ls-tree -rz --name-only "$pre:$skill"  2>/dev/null || true
              git ls-tree -rz --name-only "$post:$skill" 2>/dev/null || true
            } | sort -zu )
  exit "$conflicted"
) }

# ---------------------------------------------------------------- protection

# protect_skills <pre> <post> <prelock-file>
# Detect which skills you edited, merge each against the version you had
# installed, and commit the result — but ONLY when nothing is left conflicted.
# A conflict ends the run with the markers sitting uncommitted in the working
# tree, so the hand merge happens on the real files and the commit that follows
# records the resolution, never the markers.
# Sets the globals `merged`, `conflicted`, `nobase` and `report`.
# Every git call below runs on the working tree, so the FIRST thing it does is
# cd into $SKILLS. main() is already there, but a caller that is not (a test,
# a sourced shell) would otherwise have the protection loop stage and COMMIT
# whatever repo it happened to be standing in.
protect_skills(){
  cd "$SKILLS" || return 1
  local PRE=$1 POST=$2 prelock=$3 s base rc out name hash cur
  # Protected set = AUTO-DETECTED (pre-update on-disk tree diverged from the
  # PRE-UPDATE lock hash, i.e. from the upstream version you had installed)
  # UNION any manual entries in .protected-skills, which force a whole-file keep
  # (no merge) for the skills they name.
  local -A PROT BASEHASH MANUAL
  if [ -s "$prelock" ]; then
    while IFS=$'\t' read -r name hash; do
      [ -z "$name" ] && continue
      cur=$(git rev-parse "$PRE:$name" 2>/dev/null) || continue   # tree SHA of your pre-update version
      BASEHASH[$name]=$hash
      [ "$cur" != "$hash" ] && PROT[$name]=1                       # diverged from installed upstream => you edited it
    done < "$prelock"
  fi
  if [ -f .protected-skills ]; then
    while read -r s || [ -n "$s" ]; do   # || : a hand-edited file may lack its final newline
      [[ -z "$s" || "$s" == \#* ]] && continue
      PROT[$s]=1; MANUAL[$s]=1   # an explicit "keep mine" beats any merge base
    done < .protected-skills
  fi

  merged=(); conflicted=(); nobase=(); report=""
  for s in "${!PROT[@]}"; do
    if [ ! -e "$s" ]; then
      # upstream removed the skill outright. Your edited copy is still in PRE —
      # restore it rather than letting it disappear, and let the digest rule.
      if git cat-file -e "$PRE:$s" 2>/dev/null; then
        git checkout "$PRE" -- "$s"; nobase+=("$s")
      fi
      continue
    fi
    if git diff --quiet "$PRE" "$POST" -- "$s"; then continue; fi   # upstream left it alone
    if [ -z "${MANUAL[$s]:-}" ] && base=$(resolve_base_tree "${BASEHASH[$s]:-}"); then
      rc=0; out=$(merge_skill "$s" "$base" "$PRE" "$POST") || rc=$?
      if [ "$rc" -gt 1 ]; then
        # the merge itself broke — don't pass a half-merged tree off as a result
        echo "merge failed for $s (exit $rc) — keeping your version whole-file" >&2
        git checkout "$PRE" -- "$s"; nobase+=("$s"); continue
      fi
      if [ "$rc" -eq 0 ]; then merged+=("$s"); else conflicted+=("$s"); fi
      if [ -n "$out" ]; then                       # nothing to say when no file needed a decision
        report+="$s  (base ${base:0:9})"$'\n'
        report+=$(printf '%s\n' "$out" | awk -F'\t' 'NF>=2{printf "  %-9s %s%s\n", $1, $2, ($3 == "" ? "" : "   <- " $3)}')$'\n'
      fi
    else
      # Either you asked for whole-file protection in .protected-skills, or there
      # is no base to merge from and guessing one is worse than not merging. Keep
      # YOUR version; the upstream delta stays one `git diff PRE POST` away.
      git checkout "$PRE" -- "$s"; nobase+=("$s")
    fi
  done

  # The commit gate. Markers in the tree must never reach a commit.
  [ ${#conflicted[@]} -eq 0 ] || return 0
  git add -A
  if ! git diff --cached --quiet HEAD; then
    git commit -qm "merge local edits with upstream (three-way)" >/dev/null
  fi
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
protect_skills "$PRE" "$POST" "$PRELOCK"
rm -f "$PRELOCK"

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
  echo "CONFLICTED — files below carry conflict markers (${#conflicted[@]}): ${conflicted[*]}"
  echo "NOTHING WAS COMMITTED. Resolve every marker in the working tree, then:"
  echo "  git -C $SKILLS add -A && git -C $SKILLS commit -m 'merge local edits with upstream'"
fi
if [ ${#nobase[@]} -gt 0 ]; then
  echo "Kept whole-file, NOT merged — manual override or no merge base (${#nobase[@]}):"
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
