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
# Every needle is scoped to the section that owns the rule, and each of those
# sections must exist as a heading: a heading is a claim on its own, where a
# needle loose in the file is satisfied by any sentence anywhere — including
# the sentence that says the opposite. That is this guard's ceiling and it is
# worth stating: a substring witnesses that the rule is written down, never
# that the prose around it means it.
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

# One `## ` section of merge-tail.md, by its exact heading, flattened. The
# heading itself and the next one are dropped, so a needle can never be
# satisfied by the neighbouring section's prose.
section() {
  awk -v want="## $1" '
    $0 == want { inside = 1; next }
    inside && /^## / { exit }
    inside { print }' "$tail_doc" | flatten
}

# Scoped to `### The merge` **step 5** — the step that runs cleanup, and the
# step #454's controller was reading. The whole section is 200 lines long, so
# a needle loose in it is satisfied by prose nowhere near the cleanup call.
merge_step5="$(sed -n '/^###[[:space:]]*The merge[[:space:]]*$/,/^##[[:space:]]/p' "$implement" \
  | sed -n '/^5\.[[:space:]]/,/^6\.[[:space:]]/{/^6\.[[:space:]]/d; p}' | flatten)"
[ -n "$merge_step5" ] || { echo "FAIL: implement/SKILL.md § The merge has no step 5" >&2; exit 1; }

fail=0

check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Each rule's section must exist as a heading, checked here rather than
# inside `section`: an assignment inside a command substitution runs in a
# subshell and never reaches this shell's `fail`.
for heading in 'First PR to land wins' \
               'Generated artifacts are regenerated, never hand-merged' \
               'An escaped collision is a defect in the include grammar' \
               'Answer, then merge, then cleanup'; do
  grep -qxF "## $heading" "$tail_doc" || {
    echo "FAIL: references/merge-tail.md has no section: ## $heading" >&2
    fail=1
  }
done

# Rule 0: this is executable policy again. The parked stub pointed at a
# retired tool and told a controller to read `git show` for the rest.
case "$tail_text" in
  *"**Parked**"*) echo "FAIL: references/merge-tail.md is still parked" >&2; fail=1 ;;
esac

# Rule 1: first PR to land wins, and the loser rebases rather than being
# re-reviewed or re-cut. `rebase` alone was a free pass — every inversion of
# this rule still contains the word.
first_pr="$(section 'First PR to land wins')"
check_in "$first_pr" 'first PR to land wins' 'references/merge-tail.md § First PR to land wins'
check_in "$first_pr" 'The other rebases onto the default branch' 'references/merge-tail.md § First PR to land wins'
check_in "$first_pr" 'force-with-lease' 'references/merge-tail.md § First PR to land wins' 

# Rule 2: generated artifacts are regenerated, never hand-merged, and the
# side taken for them is the default branch's. The heading carries the rule,
# so it is asserted by name.
generated="$(section 'Generated artifacts are regenerated, never hand-merged')"
check_in "$generated" 'regenerate' 'references/merge-tail.md § Generated artifacts'
check_in "$generated" 'checkout --ours' 'references/merge-tail.md § Generated artifacts'
# Both sides named, because `--ours` inside a rebase is the upstream and a
# doc that says "take main's side" without that is read backwards.
check_in "$generated" '--theirs' 'references/merge-tail.md § Generated artifacts'
check_in "$generated" 'inverted' 'references/merge-tail.md § Generated artifacts'
check_in "$generated" 'Generator' 'references/merge-tail.md § Generated artifacts'
# Rule 2b (Codex pass on PR #930): the recipe stages the paths it named and
# reads the staged diff, because it ends in a force-push. `git add -A` here
# publishes whatever untracked file the workspace happened to hold.
check_in "$generated" 'git add --' 'references/merge-tail.md § Generated artifacts'
check_in "$generated" 'git diff --cached' 'references/merge-tail.md § Generated artifacts'
check_in "$generated" 'Never `git add -A` here' 'references/merge-tail.md § Generated artifacts' 

# Rule 3: a collision that escaped the closure is a defect in the repo's
# declared include grammar, and it is filed against the repo — otherwise the
# same two files collide on every run and the closure never learns.
escaped="$(section 'An escaped collision is a defect in the include grammar')"
check_in "$escaped" 'escaped the closure' 'references/merge-tail.md § An escaped collision'
check_in "$escaped" 'Include closure' 'references/merge-tail.md § An escaped collision'
check_in "$escaped" 'AGENTS.md' 'references/merge-tail.md § An escaped collision'
check_in "$escaped" 'file-ticket' 'references/merge-tail.md § An escaped collision' 

# Rule 4: the ordering, stated as the literal order — and stated as a
# **heading**, which `section` asserts by name. A clause can be negated in
# the sentence around it; a heading is the section's claim.
ordering="$(section 'Answer, then merge, then cleanup')"
check_in "$ordering" 'answer, then merge, then cleanup' 'references/merge-tail.md § Answer, then merge, then cleanup'
check_in "$ordering" 'cleanup is the last act' 'references/merge-tail.md § Answer, then merge, then cleanup' 

# Rule 5: the cleanup edge specifically. Answering before the *merge* is not
# the rule: cleanup is what closes the pane, so a tail that answers between
# merge and cleanup is correct and one that answers after cleanup is lost.
# Without this, a doc could satisfy rule 4 and still leave cleanup free to
# run ahead of a later answer.
check_in "$ordering" 'closes its pane' 'references/merge-tail.md § Answer, then merge, then cleanup'
check_in "$ordering" 'not merely before the merge' 'references/merge-tail.md § Answer, then merge, then cleanup' 

# Rule 5b: the section may not state the rule and then withdraw it. A
# substring guard witnesses that a rule is written down, never that the prose
# means it, and the section headings above are the main defence. This is the
# cheap second one: a blacklist of the ways the ordering was taken back when
# this guard was adversarially mutated (#896 verification pass). It closes
# those and claims nothing about the ones nobody has written yet.
refuse_in() {
  local haystack="$1" pattern="$2" where="$3"
  if printf '%s' "$haystack" | grep -qiE "$pattern"; then
    echo "FAIL: $where states the rule and then takes it back (/$pattern/)" >&2
    fail=1
  fi
}
refuse_in "$ordering" \
  'not true that|clean ?up first|answer later|no longer the rule|is obsolete|not a real constraint' \
  'references/merge-tail.md § Answer, then merge, then cleanup'

# Rule 6: the reader behind the ordering is reachable from the prose.
check_in "$ordering" 'loop.py landing' 'references/merge-tail.md § Answer, then merge, then cleanup' 

# Rule 7: the single-ticket lane carries the same ordering at the step that
# runs cleanup. `/implement`'s § The merge is where the #454 controller was
# reading, and it ordered check, Codex pass, merge, cleanup and said nothing
# about answering the worker.
check_in "$merge_step5" 'outstanding question' 'implement/SKILL.md § The merge step 5'
check_in "$merge_step5" 'before cleanup' 'implement/SKILL.md § The merge step 5'
check_in "$merge_step5" 'not merely before the merge' 'implement/SKILL.md § The merge step 5'
check_in "$merge_step5" 'merge-tail.md' 'implement/SKILL.md § The merge step 5'

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/merge-tail.test.sh"
else
  exit 1
fi
