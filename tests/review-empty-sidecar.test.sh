#!/usr/bin/env bash
# Wording test for #1257: implement/fix-check.sh passes a heavy PR whose
# reviewers found nothing only when all three findings sidecars exist, empty,
# each beside its completion marker, and refuses an absent one. That is only
# reachable if each axis reviewer is told to write its sidecar on every run,
# empty when it found nothing. The instruction lives in multi-axis-code-review/SKILL.md § 4; this
# pins it there (and not merely anywhere in the file), so deleting it is red.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

fail() { echo "FAIL: $*"; exit 1; }

# Section 4's body: from its heading to the next `### ` heading. An empty
# extraction means the heading moved, which is not a pass.
sec4=$(awk '/^### 4\. /{on=1; next} /^### /{on=0} on' multi-axis-code-review/SKILL.md)
[ -n "$sec4" ] || fail "§ 4 heading not found in multi-axis-code-review/SKILL.md"
flat=$(printf '%s' "$sec4" | tr '\n' ' ' | tr -s ' ')

need() { # <fixed phrase> <what it pins>
  printf '%s' "$flat" | grep -qF -- "$1" || fail "§ 4 lacks \"$1\" ($2)"
}
need "on every run" "the sidecar is written on every run"
need "empty file when it found nothing" "zero findings writes an empty file"
echo "ok: § 4 tells each axis to write an empty sidecar on zero findings"

# The standing brief carries its own copy of the sidecar rule, so a prompt
# that drops the line still yields a sidecar; the empty-file rule must ride
# with it or that fallback writes nothing on a clean round.
brief=$(tr '\n' ' ' <flow/claude/agents/diff-reviewer.md | tr -s ' ')
printf '%s' "$brief" | grep -qF "an empty file when you found nothing" ||
  fail "flow/claude/agents/diff-reviewer.md lacks the empty-sidecar rule"
echo "ok: the standing brief carries it too"

# #1401: the empty sidecar is accepted only beside the reviewer's completion
# marker, so both the skill and the standing brief must tell a reviewer to
# write it, and § 4 must say why an empty file alone is not enough.
need "completion marker" "the marker is named"
need "findings-<axis>-<n>.done" "the marker's file name"
need "a reviewer that crashed" "why an empty sidecar alone is not enough"
printf '%s' "$brief" | grep -qF "completion marker" ||
  fail "flow/claude/agents/diff-reviewer.md lacks the completion-marker rule"
echo "ok: both tell each axis to write the completion marker"
