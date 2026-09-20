#!/usr/bin/env bash
# Guards #893: the dispatch loop is written down once, in `burndown/SKILL.md`
# § The loop, and the rules a run got wrong by hand are stated there rather
# than left to a controller's judgment — the worktree refusal, the frozen
# candidate set, continuous refill, the hub-landing trigger, the exclusion
# rule and its two consequences, the box check, and the opening report's
# clumping announcement. Prose assertions no Python harness can make; the
# reader's behaviour is tested in burndown/loop_test.py.
# It also guards the other half of #779: the loop is the single home, so it
# restates none of `implement-dispatch`'s, `merge-cleanup`'s or herdr's own
# grammar — it points at them.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reference="$here/references/loop.md"

for f in "$skill" "$reference"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# Scoped to `## The loop` and its subsections, so a needle this generic is
# never satisfied by prose elsewhere in the skill. Runs to the next `## `.
section="$(sed -n '/^##[[:space:]]*The loop[[:space:]]*$/,/^##[[:space:]]/{/^##[[:space:]]*The loop[[:space:]]*$/d; /^##[[:space:]][^#]/d; p}' "$skill")"
[ -n "$section" ] || { echo "FAIL: burndown/SKILL.md has no § The loop" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }
loop_text="$(printf '%s\n' "$section" | flatten)"
reference_text="$(flatten <"$reference")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: where the controller runs, and the refusal that keeps a worker from
# reading itself as one.
check_in "$loop_text" 'default branch' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'worktree' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'worker' 'burndown/SKILL.md § The loop'
check_in "$loop_text" '--repo' 'burndown/SKILL.md § The loop'

# Rule 2: the candidate set is frozen at an exploration that covers the whole
# queue, and the one ticket that may join a run in flight is named.
check_in "$loop_text" 'frozen' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'whole queue' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'stuck' 'burndown/SKILL.md § The loop'

# Rule 3: refill is continuous and recomputed at each landing — no waves.
check_in "$loop_text" 'continuous' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'each landing' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'no waves' 'burndown/SKILL.md § The loop'

# Rule 4: closure freshness — one hop at each dispatch, full re-exploration
# only after a hub landing.
check_in "$loop_text" 'one hop' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'hub' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'in-flight' 'burndown/SKILL.md § The loop'

# Rule 5: the exclusion rule and **both** consequences, stated out loud — a
# controller reading only "open, unblocked, unclaimed" dispatches into a
# collision, and neither consequence is visible from the frontier's own
# definition.
check_in "$loop_text" 'out of ticket order' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'whole family' 'burndown/SKILL.md § The loop'

# Rule 6: the box check, before every dispatch, with both readings and both
# caps named.
check_in "$loop_text" 'before every dispatch' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'uptime' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'free -g' 'burndown/SKILL.md § The loop'
check_in "$loop_text" '28' 'burndown/SKILL.md § The loop'
check_in "$loop_text" '24 GB' 'burndown/SKILL.md § The loop'

# Rule 7: the opening report announces which clumping mode the run got, and
# all three declaration states are told apart — a controller reading
# "conservative" has to know whether the repo said nothing or said None.
check_in "$loop_text" 'opening report' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'declared None' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'silence' 'burndown/SKILL.md § The loop'

# Rule 8: on resume, one message per live unlanded worker, and the herdr name
# is resolved to an address at send time rather than stored.
check_in "$loop_text" 'one message' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'send time' 'burndown/SKILL.md § The loop'

# Rule 8b: the loop writes what resume reads back — a dispatched clump's
# workspace and agent — and re-resolves closures through the clumper. Without
# either, step 1's announce bucket is empty and step 5 checks stale closures.
check_in "$loop_text" 'runfile.py clump' 'burndown/SKILL.md § The loop'
# The re-resolve step names the clumper itself — not merely somewhere in the
# section, which step 3's announcement line already satisfied.
check_in "$loop_text" 'through `closure.py`' 'burndown/SKILL.md § The loop'

# Rule 9: the reader is reachable, and so is the reference that holds the why.
check_in "$loop_text" 'burndown/loop.py' 'burndown/SKILL.md § The loop'
check_in "$loop_text" 'references/loop.md' 'burndown/SKILL.md § The loop'

# Rule 10: the single home restates no other lane's grammar. Any of those
# three command names followed by a flag or a placeholder argument is a
# restatement; naming one bare, with a pointer, is the point.
if echo "$loop_text" | grep -qE '(implement-dispatch|merge-cleanup|herdr [a-z]+)[^.,)`]*[ `](--|<)'; then
  echo "FAIL: § The loop restates another lane's grammar:" >&2
  echo "$loop_text" | grep -oE '(implement-dispatch|merge-cleanup|herdr [a-z]+)[^.,)`]*[ `](--|<)[^ ]*' >&2
  fail=1
fi
check_in "$loop_text" 'implement/SKILL.md' 'burndown/SKILL.md § The loop'

# Rule 11: the reference carries the evidence the rules came from, so the next
# reader can weigh them rather than only obey them.
check_in "$reference_text" '#781' references/loop.md
check_in "$reference_text" 'line-kind.js' references/loop.md
check_in "$reference_text" 'out of ticket order' references/loop.md
check_in "$reference_text" 'hub' references/loop.md
check_in "$reference_text" 'send time' references/loop.md

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/loop-steps.test.sh"
else
  exit 1
fi
