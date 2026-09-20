#!/usr/bin/env bash
# Guards #891: the clumper reads a *declaration*, so the declaration has to be
# written down where both ends can read it — `burndown/references/closure.md`
# for the grammar, `AGENTS.md` for this repo's own answer, and
# `burndown/SKILL.md` for the run that must announce which mode it got. On
# #781 two workers collided over a shared `#include` that neither ticket
# named, and the run's report said nothing about how it had clumped them.
# This is a prose assertion over three docs — there is no harness that runs a
# skill's own prose. The resolver's behaviour is tested in
# burndown/closure_test.py.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`: a caller's leaked
# GIT_DIR/GIT_WORK_TREE would point that at the caller's repo (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
grammar="$here/references/closure.md"
skill="$here/SKILL.md"
agents="$here/../AGENTS.md"

for f in "$grammar" "$skill" "$agents"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

flatten() { tr '\n' ' ' | tr -s ' '; }

grammar_text="$(flatten <"$grammar")"
skill_text="$(flatten <"$skill")"
# Scope the AGENTS.md needles to its own `### Include closure` section: a
# phrase this generic must not be satisfied by unrelated prose elsewhere.
agents_text="$(sed -n '/^#\{1,6\}[[:space:]]*Include closure/,/^#\{1,6\}[[:space:]]*[A-Z]/p' "$agents" | flatten)"
[ -n "$agents_text" ] || { echo "FAIL: AGENTS.md has no Include closure section" >&2; exit 1; }

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: the grammar doc specifies the declaration a repo writes — the
# heading, the directive template, and the generator command.
check_in "$grammar_text" '## Include closure' references/closure.md
check_in "$grammar_text" '**Directive**' references/closure.md
check_in "$grammar_text" '**Generator**' references/closure.md
check_in "$grammar_text" '<path>' references/closure.md

# Rule 2: all three answers are stated, and the report tells them apart. A
# controller reading "conservative" has to know whether the repo said nothing
# or said None.
check_in "$grammar_text" 'no-include-graph' references/closure.md
check_in "$grammar_text" 'directory subtree' references/closure.md
check_in "$grammar_text" 'opening report' references/closure.md

# Rule 3: one hop is stated as a cost ceiling, and the generator is never run.
check_in "$grammar_text" 'One hop' references/closure.md
check_in "$grammar_text" 'reported, never' references/closure.md
check_in "$grammar_text" 'per candidate per wave' references/closure.md

# Rule 4: the reader is reachable from the skill that owns it, and the skill
# says the opening report carries the announcement.
check_in "$skill_text" 'references/closure.md' burndown/SKILL.md
check_in "$skill_text" 'closure.py' burndown/SKILL.md
check_in "$skill_text" 'opening report' burndown/SKILL.md

# Rule 5: this repo declares its own answer, and says what would change it —
# so the next person to add a generator knows the section is theirs to update.
check_in "$agents_text" 'None' AGENTS.md
check_in "$agents_text" '**Directive**:' AGENTS.md
check_in "$agents_text" '**Generator**:' AGENTS.md
check_in "$agents_text" 'burndown/references/closure.md' AGENTS.md

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/closure-declaration.test.sh"
else
  exit 1
fi
