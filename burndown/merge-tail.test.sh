#!/usr/bin/env bash
# Guards #896: the merge tail — what a controller does when two in-flight
# branches turn out to touch the same files, what an escaped collision owes
# the repo's include grammar, and the rule that every outstanding worker
# question is answered **before** cleanup. Prose assertions no Python harness
# can make; the ordering itself has a reader behind it, tested in
# burndown/loop_test.py.
# On #781 the procedure worked and went unwritten, and on `#454` a controller
# merged, ran `merge-cleanup`, and then sent the ruling its worker had asked
# for — to a pane cleanup had already closed.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tail_doc="$here/references/merge-tail.md"
implement="$here/../implement/SKILL.md"

for f in "$tail_doc" "$implement"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

flatten() { tr '\n' ' ' | tr -s ' '; }
tail_text="$(flatten <"$tail_doc")"
# Scoped to `### The merge` and its steps, so needles this generic are never
# satisfied by prose elsewhere in a skill this long. Runs to the next `## `.
merge_section="$(sed -n '/^###[[:space:]]*The merge[[:space:]]*$/,/^##[[:space:]]/p' "$implement" | flatten)"
[ -n "$merge_section" ] || { echo "FAIL: implement/SKILL.md has no § The merge" >&2; exit 1; }

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 0: this is executable policy again. The parked stub pointed at a
# retired tool and told a controller to read `git show` for the rest.
case "$tail_text" in
  *"**Parked**"*) echo "FAIL: references/merge-tail.md is still parked" >&2; fail=1 ;;
esac

# Rule 1: first PR to land wins, and the loser rebases rather than being
# re-reviewed or re-cut.
check_in "$tail_text" 'first PR to land wins' references/merge-tail.md
check_in "$tail_text" 'rebase' references/merge-tail.md

# Rule 2: generated artifacts are regenerated, never hand-merged, and the
# side taken for them is the default branch's.
check_in "$tail_text" 'regenerate' references/merge-tail.md
check_in "$tail_text" 'never hand-merged' references/merge-tail.md
check_in "$tail_text" 'checkout --ours' references/merge-tail.md
# Both sides named, because `--ours` inside a rebase is the upstream and a
# doc that says "take main's side" without that is read backwards.
check_in "$tail_text" '--theirs' references/merge-tail.md
check_in "$tail_text" 'Generator' references/merge-tail.md

# Rule 3: a collision that escaped the closure is a defect in the repo's
# declared include grammar, and it is filed against the repo — otherwise the
# same two files collide on every run and the closure never learns.
check_in "$tail_text" 'escaped the closure' references/merge-tail.md
check_in "$tail_text" 'Include closure' references/merge-tail.md
check_in "$tail_text" 'AGENTS.md' references/merge-tail.md
check_in "$tail_text" 'file-ticket' references/merge-tail.md

# Rule 4: the ordering, stated as the literal order — a reordering of the
# three steps fails here and in loop_test.py, which is what makes this a
# gate rather than a word count.
check_in "$tail_text" 'answer, then merge, then cleanup' references/merge-tail.md
check_in "$tail_text" 'cleanup is the last act' references/merge-tail.md

# Rule 5: the cleanup edge specifically. Answering before the *merge* is not
# the rule: cleanup is what closes the pane, so a tail that answers between
# merge and cleanup is correct and one that answers after cleanup is lost.
# Without this, a doc could satisfy rule 4 and still leave cleanup free to
# run ahead of a later answer.
check_in "$tail_text" 'closes its pane' references/merge-tail.md
check_in "$tail_text" 'not merely before the merge' references/merge-tail.md

# Rule 6: the reader behind the ordering is reachable from the prose.
check_in "$tail_text" 'loop.py landing' references/merge-tail.md

# Rule 7: the single-ticket lane carries the same ordering at the step that
# runs cleanup. `/implement`'s § The merge is where the #454 controller was
# reading, and it ordered check, Codex pass, merge, cleanup and said nothing
# about answering the worker.
check_in "$merge_section" 'outstanding question' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'before cleanup' 'implement/SKILL.md § The merge'
check_in "$merge_section" 'merge-tail.md' 'implement/SKILL.md § The merge'

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/merge-tail.test.sh"
else
  exit 1
fi
