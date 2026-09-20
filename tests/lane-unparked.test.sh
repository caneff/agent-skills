#!/usr/bin/env bash
# The finish-line check for #899: the multi-worker lane is live, and reachable.
#
# Two assertions, and the second is the one that matters. (1) No parked marker
# survives anywhere in the skills tree — the lane is on. (2) From each of the
# two lane skills, following only the links those skills actually carry, a
# reader arrives at the run file, the frontier reader and the closure
# resolver. Every module in map #776 landed unreachable by construction and
# two Codex passes called that a no-ship, disputed on the grounds that this
# ticket fixes it; the reachability half is what makes those disputes honest.
#
# Fail-closed by construction (#899's brief; the map's recurring defect class
# is an absent answer read as a benign one). "Zero matches" is the success
# condition for every marker here, and a grep that could not run looks exactly
# like a grep that found nothing. So before trusting any silence:
#   - every marker pattern must first match the fixture that plants it, or the
#     pattern is dead and the check says so instead of passing;
#   - the swept file set must clear a floor, or a broken `git ls-files` reads
#     as a clean tree;
#   - reachability has a negative control, or a matcher that matches anything
#     reads as a wired-up lane.
#
# Scope note: the skills tree only — every git-tracked file under a directory
# that has a SKILL.md. `docs/research/` is the project's record of what was
# true on a date, including the parked-state disputes that are this trial's
# evidence, and is deliberately not swept.
#
# GIT_* scrubbed and the root taken from BASH_SOURCE: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point git at the caller's repo (#620).
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1

fixture="tests/fixtures/lane-unparked/parked-sample.md"
# Minimum swept files. The tree carries 79 skills and thousands of files; a
# sweep that collapses to a handful has lost its input, not found a clean tree.
FLOOR=200

fail=0
note() { echo "FAIL: $*" >&2; fail=1; }

# Each marker is a POSIX ERE plus the human name the failure reports. The
# contract every one of them meets, and the reason the frontmatter key
# `disable-model-invocation: true` is NOT on this list: a parked marker is a
# string that appears in the parked files and in no live skill. That key sits
# in 53 of this repo's 79 SKILL.md files, `implement/SKILL.md` among them, so
# it marks "not auto-invocable", never "parked" — and it predates the parking
# commit 207fee4 (#752) in both lane skills. A marker added here without that
# property turns this check red across half the tree, which is why the
# zero-match assertion below reports the files it found rather than a count.
markers=(
  'frontmatter description|^description: "Parked'
  'parked banner|^> \*\*Parked\*\*'
  'parked-with-the-rest note|parked with the rest of'
  'parked-along-with note|[Pp]arked along with the rest of'
  'awaiting-the-rebuild note|until the (multi-worker )?lane is (rebuilt|unparked)'
  'written-against-the-rebuild note|against the lane being rebuilt'
  'skill-is-parked note|this skill is parked'
  'pre-park text pointer|git show 7c7eb30:'
)

# --- The swept set -----------------------------------------------------------
mapfile -t skill_dirs < <(git ls-files -- '*/SKILL.md' | cut -d/ -f1 | sort -u)
if [ "${#skill_dirs[@]}" -eq 0 ]; then
  echo "FAIL: no skill directories found — git ls-files gave nothing" >&2
  exit 1
fi
mapfile -t swept < <(git ls-files -- "${skill_dirs[@]/%//}")
if [ "${#swept[@]}" -lt "$FLOOR" ]; then
  echo "FAIL: swept ${#swept[@]} files across ${#skill_dirs[@]} skills, under the floor of $FLOOR" >&2
  exit 1
fi

# --- Positive control, before any silence is trusted --------------------------
[ -f "$fixture" ] || { echo "FAIL: missing positive-control fixture $fixture" >&2; exit 1; }
for m in "${markers[@]}"; do
  name="${m%%|*}"; pattern="${m#*|}"
  grep -qE -- "$pattern" "$fixture" ||
    note "marker '$name' matches nothing in $fixture — the pattern is dead, so its silence about the tree proves nothing"
done
[ "$fail" = 0 ] || { echo "--- the check cannot see; not reporting on the tree ---" >&2; exit 1; }

# --- Assertion 1: no parked marker survives in the skills tree ---------------
for m in "${markers[@]}"; do
  name="${m%%|*}"; pattern="${m#*|}"
  hits="$(grep -InE -- "$pattern" "${swept[@]}" 2>/dev/null)"
  if [ -n "$hits" ]; then
    note "parked marker '$name' still in the skills tree:"
    printf '%s\n' "$hits" | sed 's/^/    /' >&2
  fi
done

# --- Assertion 2: each lane skill reaches its three modules ------------------
# Reachability is the reader's own route: start at the skill's SKILL.md and
# follow the relative Markdown links it carries, transitively. A module named
# only from a test file or from a research doc is not reachable from the skill.
links_of() { # $1 = repo-relative file; prints repo-relative link targets
  local f="$1" dir t
  dir="$(dirname "$f")"
  grep -oE '\]\([^)]+\)' "$f" 2>/dev/null |
    sed -e 's/^](//' -e 's/)$//' -e 's/#.*$//' |
    while IFS= read -r t; do
      [ -n "$t" ] || continue
      case "$t" in
        http:*|https:*|mailto:*) continue ;;
        '~/.agents/skills/'*) printf '%s\n' "${t#\~/.agents/skills/}" ;;
        /*|'~'*) continue ;;
        *) realpath -m --relative-to="$root" "$root/$dir/$t" ;;
      esac
    done
}

reachable_from() { # $1 = start file; prints every repo-relative file reachable
  local start="$1" f t
  local -a queue=("$start")
  local -A visited=()
  while [ "${#queue[@]}" -gt 0 ]; do
    f="${queue[0]}"; queue=("${queue[@]:1}")
    [ -n "${visited[$f]:-}" ] && continue
    visited["$f"]=1
    [ -f "$f" ] || continue
    printf '%s\n' "$f"
    while IFS= read -r t; do
      [ -n "$t" ] && queue+=("$t")
    done < <(links_of "$f")
  done
}

# The three modules by path, not by bare basename: `closure.py` alone would be
# satisfied by any prose saying the word.
required=(
  'run file|burndown/runfile.py'
  'frontier reader|burndown/frontier.py'
  'closure resolver|burndown/closure.py'
)
# Negative control. A real module path, spelled for a file that does not exist:
# if this is "reachable", the matcher below matches anything and every pass
# above it is meaningless.
absent='burndown/no-such-resolver.py'

for skill in burndown implement-spec; do
  start="$skill/SKILL.md"
  [ -f "$start" ] || { note "$start does not exist"; continue; }
  mapfile -t docs < <(reachable_from "$start")
  if [ "${#docs[@]}" -lt 2 ]; then
    note "$skill reaches only ${#docs[@]} file(s) — it carries no followable links, so nothing below is a real reachability result"
    continue
  fi
  text="$(cat "${docs[@]}" 2>/dev/null)"
  for r in "${required[@]}"; do
    name="${r%%|*}"; path="${r#*|}"
    case "$text" in
      *"$path"*) ;;
      *) note "$skill does not reach the $name ($path) through its own links; it reaches ${#docs[@]} files: ${docs[*]}" ;;
    esac
  done
  case "$text" in
    *"$absent"*) note "negative control failed: $skill 'reaches' $absent, which does not exist — the reachability matcher matches anything" ;;
  esac
done

[ "$fail" = 0 ] || exit 1
echo "ok — lane live: ${#swept[@]} files swept across ${#skill_dirs[@]} skills, ${#markers[@]} markers clear, burndown and implement-spec each reach all ${#required[@]} modules"
