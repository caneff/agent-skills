#!/usr/bin/env bash
# The finish-line check for #899: the multi-worker lane is live, and reachable.
#
# Two assertions, and the second is the one the ticket cares about. (1) No
# parked mark, and no pointer left saying the lane is not live, survives in
# the skills tree. (2) From each of the two lane skills, following only the
# links those skills actually carry, a reader arrives at the run file, the
# frontier reader and the closure resolver — and those three modules exist.
# Every module in map #776 landed unreachable by construction and two Codex
# passes called that a no-ship, disputed on the grounds that this ticket fixes
# it; assertion 2 is what makes those disputes honest.
#
# Fail-closed by construction, because "zero matches" is the success condition
# for almost everything here and a grep that could not run looks exactly like
# a grep that found nothing. The map's recurring defect class is an absent or
# malformed answer read as a benign one, and the first draft of this file had
# it twice: the sweep discarded grep's exit status, so 380 unreadable files
# reported a clean tree, and assertion 2 was a substring search over
# concatenated prose, so it passed with all three modules deleted. Hence, in
# order, before any silence is trusted:
#   - every pattern must match the fixture that plants it, or it is dead;
#   - every swept path must be a readable file, and the set must contain
#     known members and clear a floor;
#   - every grep's exit status is read: 0 found, 1 clean, anything else is a
#     failure to look, reported as one;
#   - each module must exist as a file AND be named by a reachable doc, and
#     no link in the graph may dangle;
#   - the negative control is a real module that no lane doc names, not a
#     path nobody ever wrote.
#
# Scope: the skills tree only — every git-tracked file under a directory that
# has a SKILL.md. `docs/research/` is the project's record of what was true on
# a date, including the parked-state disputes that are this trial's evidence,
# and is deliberately not swept; the ticket's own wording is "a grep over the
# skills tree".
#
# GIT_* scrubbed and the root taken from BASH_SOURCE: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point git at the caller's repo (#620).
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1

fixture="tests/fixtures/lane-unparked/parked-sample.md"
# A tripwire, not a measurement: the tree carries 79 skills and 400-odd files,
# and the per-file readability check below is what actually catches a hollowed
# working tree. This only catches a sweep that has lost its input wholesale.
FLOOR=350
# Members the swept set must contain. A positive control on the set itself:
# a sweep that silently stops covering the two skills under test would
# otherwise report a clean tree with a straight face.
must_sweep=(burndown/SKILL.md implement-spec/SKILL.md burndown/references/run-file.md)

fail=0
note() { echo "FAIL: $*" >&2; fail=1; }

# `AGENTS.md` § Skill frontmatter defines parked state and the property any
# detector of it must have — it matches exactly the parked files and no live
# skill. That section is also why `disable-model-invocation: true` is on
# neither list below.
#
# These two are the canonical marks that section names: parked is marked
# these two ways and only these two, so unparking is done when both are gone.
marks=(
  'Parked: description prefix|^description: "Parked'
  'parked banner|^> \*\*Parked\*\*'
)
# These six are not marks. They are the pointers the parking commit 207fee4
# (#752) left scattered through the lane's prose, each of which went on saying
# the lane was not live after the two marks came off — the ticket's second
# criterion, "no doc still points at the parked state". Kept in their own list
# so a reader is not told the repo has eight ways to park a skill.
stale_pointers=(
  'parked-with-the-rest note|parked with the rest of'
  'parked-along-with note|[Pp]arked along with the rest of'
  'awaiting-the-rebuild note|until the (multi-worker )?lane is (rebuilt|unparked)'
  'written-against-the-rebuild note|against the lane being rebuilt'
  'skill-is-parked note|this skill is parked'
  'pre-park text pointer|git show 7c7eb30:'
)
patterns=("${marks[@]}" "${stale_pointers[@]}")

# --- The swept set -----------------------------------------------------------
mapfile -t skill_dirs < <(git ls-files -- '*/SKILL.md' | cut -d/ -f1 | sort -u)
if [ "${#skill_dirs[@]}" -eq 0 ]; then
  echo "FAIL: no skill directories found — git ls-files gave nothing" >&2
  exit 1
fi
# -z and `mapfile -d ''`: `git ls-files` renders a path holding a newline or a
# quote in C-quoted form, and a quoted path is one grep cannot open — which,
# before the status check below, was a silent pass.
mapfile -d '' -t swept < <(git ls-files -z -- "${skill_dirs[@]/%//}")
if [ "${#swept[@]}" -lt "$FLOOR" ]; then
  echo "FAIL: swept ${#swept[@]} files across ${#skill_dirs[@]} skills, under the floor of $FLOOR" >&2
  exit 1
fi
for m in "${must_sweep[@]}"; do
  printf '%s\n' "${swept[@]}" | grep -qxF -- "$m" ||
    { echo "FAIL: the swept set does not contain $m — it is not sweeping the tree under test" >&2; exit 1; }
done
# The index says these files exist; the working tree is what grep reads. A
# sparse or half-materialised checkout makes every grep below exit 2, and
# before this check that was indistinguishable from a clean tree.
unreadable=()
for f in "${swept[@]}"; do [ -r "$f" ] || unreadable+=("$f"); done
if [ "${#unreadable[@]}" -gt 0 ]; then
  echo "FAIL: ${#unreadable[@]} of ${#swept[@]} swept paths are not readable files; grep cannot look at them, so silence here would prove nothing. First few: ${unreadable[*]:0:5}" >&2
  exit 1
fi

# --- Positive control: every pattern must find its planted marker ------------
[ -f "$fixture" ] || { echo "FAIL: missing positive-control fixture $fixture" >&2; exit 1; }
for p in "${patterns[@]}"; do
  name="${p%%|*}"; pattern="${p#*|}"
  grep -qE -e "$pattern" -- "$fixture" ||
    note "pattern '$name' matches nothing in $fixture — it is dead, so its silence about the tree proves nothing"
done
[ "$fail" = 0 ] || { echo "--- the check cannot see; not reporting on the tree ---" >&2; exit 1; }

# --- Assertion 1: nothing in the skills tree says the lane is parked ---------
# grep's exit status is the point: 0 found, 1 clean, >=2 failed to look. The
# third case is a failure of this check, never a clean tree.
sweep_for() { # $1 = human name, $2 = ERE, $3 = what a hit means
  local name="$1" pattern="$2" kind="$3" hits status
  hits="$(grep -InE -e "$pattern" -- "${swept[@]}" 2>&1)"; status=$?
  case "$status" in
    0) note "$kind '$name' still in the skills tree:"
       printf '%s\n' "$hits" | sed 's/^/    /' >&2 ;;
    1) ;;
    *) note "grep exited $status looking for '$name' — this check failed to look, and that is not a clean tree: $hits" ;;
  esac
}
for p in "${marks[@]}"; do sweep_for "${p%%|*}" "${p#*|}" "parked mark"; done
for p in "${stale_pointers[@]}"; do sweep_for "${p%%|*}" "${p#*|}" "stale parked-state pointer"; done

# --- Assertion 2: each lane skill reaches its three modules ------------------
# Reachability is the reader's own route: start at the skill's SKILL.md and
# follow the relative Markdown links it carries, transitively. A module named
# only from a test file or a research doc is not reachable from the skill.
links_of() { # $1 = repo-relative file; prints repo-relative link targets
  local f="$1" dir t
  dir="$(dirname "$f")"
  grep -oE '\]\([^)]+\)' -- "$f" 2>/dev/null |
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

walk_from() { # $1 = start file; prints "<found|dangling>\t<repo-relative path>"
  local start="$1" f t
  local -a queue=("$start")
  local -A visited=()
  while [ "${#queue[@]}" -gt 0 ]; do
    f="${queue[0]}"; queue=("${queue[@]:1}")
    [ -n "${visited[$f]:-}" ] && continue
    visited["$f"]=1
    if [ ! -e "$f" ]; then printf 'dangling\t%s\n' "$f"; continue; fi
    [ -f "$f" ] || continue
    printf 'found\t%s\n' "$f"
    case "$f" in
      *.md) ;;
      *) continue ;;   # only Markdown carries links worth following
    esac
    while IFS= read -r t; do
      [ -n "$t" ] && queue+=("$t")
    done < <(links_of "$f")
  done
}

# The three modules by repo path, not by bare basename: `closure.py` alone
# would be satisfied by any prose saying the word.
required=(
  'run file|burndown/runfile.py'
  'frontier reader|burndown/frontier.py'
  'closure resolver|burndown/closure.py'
)
# Negative control, and it has to be a real tracked module that no lane doc
# names — `burndown/phases.py`, referenced today only by its own tests and by
# `docs/research/`. A path nobody ever wrote could not match whatever the
# matcher did, so it proved nothing; this one fires the moment the matcher
# starts reading files the skills do not actually link. If a lane doc ever
# does link it, wire it into `required` above and pick another control.
absent='burndown/phases.py'
[ -f "$absent" ] || { echo "FAIL: negative control $absent does not exist; pick a tracked module no lane doc names" >&2; exit 1; }

for skill in burndown implement-spec; do
  start="$skill/SKILL.md"
  [ -f "$start" ] || { note "$start does not exist"; continue; }
  docs=(); dangling=()
  while IFS=$'\t' read -r state path; do
    case "$state" in found) docs+=("$path") ;; dangling) dangling+=("$path") ;; esac
  done < <(walk_from "$start")
  if [ "${#dangling[@]}" -gt 0 ]; then
    note "$skill links ${#dangling[@]} target(s) that do not exist — a reader following them arrives nowhere: ${dangling[*]}"
  fi
  if [ "${#docs[@]}" -lt 2 ]; then
    note "$skill reaches only ${#docs[@]} file(s) — it carries no followable links, so nothing below is a real reachability result"
    continue
  fi
  for r in "${required[@]}"; do
    name="${r%%|*}"; path="${r#*|}"
    # Two separate facts, and the first draft asserted neither: the module is
    # there, and some doc the reader can actually reach names it.
    [ -f "$path" ] || { note "$skill's $name does not exist at $path"; continue; }
    namer=""
    for d in "${docs[@]}"; do
      if grep -qF -e "$path" -- "$d" 2>/dev/null; then namer="$d"; break; fi
    done
    [ -n "$namer" ] ||
      note "$skill does not reach the $name ($path): none of the ${#docs[@]} files it links names it (${docs[*]})"
  done
  for d in "${docs[@]}"; do
    if grep -qF -e "$absent" -- "$d" 2>/dev/null; then
      note "negative control failed: $skill reaches $absent via $d, which no lane doc should name — either the matcher is reading files the skill does not link, or $absent is now wired in and this control needs replacing"
      break
    fi
  done
done

[ "$fail" = 0 ] || exit 1
echo "ok — lane live: ${#swept[@]} files swept across ${#skill_dirs[@]} skills, ${#marks[@]} marks and ${#stale_pointers[@]} stale pointers clear, burndown and implement-spec each reach all ${#required[@]} modules"
