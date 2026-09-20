#!/usr/bin/env bash
# Guards #898's prose: a reader nothing points at is a reader nobody runs.
# `burndown/tier.py` decides a ticket's tier by writing the `documentation`
# label onto it, so the skill that owns it has to reach it, the run's opening
# report has to name every label it wrote, and the divergence from
# `flow/claude/WORKFLOW.md` § Gate 2 has to be written down — an undocumented
# divergence reads as a bug to the next person and gets "fixed" back to the
# permissive side, which is the side that lands code with no PR.
# This is a prose assertion over two docs; the classifier's behaviour is
# tested in burndown/tier_test.py.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point that at the caller's repo (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
grammar="$here/references/tier.md"
skill="$here/SKILL.md"

for f in "$grammar" "$skill"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

flatten() { tr '\n' ' ' | tr -s ' '; }

grammar_text="$(flatten <"$grammar")"
skill_text="$(flatten <"$skill")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: the reader is reachable from the skill that owns it, and the skill
# states the direction of the error — the one thing a later editor has to
# know before relaxing the classifier.
check_in "$skill_text" 'references/tier.md' burndown/SKILL.md
check_in "$skill_text" 'tier.py' burndown/SKILL.md
check_in "$skill_text" 'only ever adds' burndown/SKILL.md

# Rule 2: the opening report names what was written. Without this line the
# skill's step 3 says nothing about labels, and a pass that wrote none reads
# exactly like a pass that never ran.
check_in "$skill_text" 'every label the exploration pass wrote' burndown/SKILL.md
check_in "$skill_text" 'labels written: none' burndown/SKILL.md

# Rule 3: the grammar doc states the seam, its four answers, and that the
# label is written on the ticket rather than carried as a flag.
check_in "$grammar_text" 'labels_to_write' references/tier.md
check_in "$grammar_text" 'The label, not a flag' references/tier.md
check_in "$grammar_text" 'names no files' references/tier.md
check_in "$grammar_text" '--remove-label' references/tier.md

# Rule 4: the divergence from § Gate 2 is stated as a divergence, with the
# `tests/all.sh` discovery as its evidence — not left for the next reader to
# discover as an inconsistency.
check_in "$grammar_text" 'Gate 2' references/tier.md
check_in "$grammar_text" 'docs/research/' references/tier.md
check_in "$grammar_text" 'tests/all.sh' references/tier.md

# Rule 5: a worker's right to raise light to heavy survives in writing. The
# reverse is what this whole reader must never enable.
check_in "$grammar_text" 'raise light to heavy' references/tier.md

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/tier-tagging.test.sh"
else
  exit 1
fi
