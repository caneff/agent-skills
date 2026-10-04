#!/usr/bin/env bash
# Guards #1401 (ADR 0004), which moved the Codex adversarial pass from the
# controller's § The merge into the worker's review wave: it runs beside the
# three axes (implement/SKILL.md § Review step 1), once, with no second pass,
# and its findings are fixed in the same fix round as the axes'. A prose
# assertion over implement/SKILL.md, not a behavioral test — no harness runs
# the skill's own prose. The record shape the pass writes is read by
# `fix-check.sh` (fix_check_test.py) and `review_ledger.py`.
# Each check is scoped to the section that owns the rule, so a phrase pasted
# elsewhere does not satisfy it: § Review (the wave), § The Codex pass (the
# block) and § The merge (which must no longer run a pass).
# Resolving via BASH_SOURCE sidesteps a caller's leaked GIT_DIR (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

review="$(sed -n '/^### Review$/,/^#### The Codex pass$/p' "$skill" | flatten)"
codex="$(sed -n '/^#### The Codex pass$/,/^### Before the PR$/p' "$skill" | flatten)"
merge="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
for pair in "§ Review:$review" "§ The Codex pass:$codex" "§ The merge:$merge"; do
  [ -n "${pair#*:}" ] || { echo "FAIL: could not extract ${pair%%:*} from implement/SKILL.md" >&2; exit 1; }
done

fail=0
check_in() { # <section text> <needle> <where>
  case "$1" in *"$2"*) ;; *) echo "FAIL: implement/SKILL.md $3 is missing: $2" >&2; fail=1 ;; esac
}
check_absent_in() { # <section text> <needle> <where>
  case "$1" in *"$2"*) echo "FAIL: implement/SKILL.md $3 still has: $2" >&2; fail=1 ;; *) ;; esac
}

# The wave: parallel, one pass, no re-review, fixed in one round.
check_in "$review" 'and the Codex pass (§ The Codex pass, below) run in parallel on the same commit' '§ Review'
check_in "$review" 'Start the Codex pass first, in the background' '§ Review'
check_in "$review" 'Nothing is fixed until every reviewer you started has finished' '§ Review'
check_in "$review" 'No second pass.' '§ Review'
check_in "$review" '`codex-gate-<k>` for the Codex pass'"'"'s k-th finding' '§ Review'
check_absent_in "$review" 'verification pass' '§ Review'

# The merge no longer runs a pass, and says nothing of a second one.
check_in "$merge" 'There is no review step here' '§ The merge'
check_absent_in "$merge" 'codex-companion' '§ The merge'
check_absent_in "$merge" 'second pass' '§ The merge'
check_absent_in "$merge" 'review-trial' '§ The merge'

# Skips: never blocks a build, and a skip is a ledger row plus a named reason.
check_in "$codex" 'Run `codex login status` first' '§ The Codex pass'
check_in "$codex" 'not part of a Codex-lane build' '§ The Codex pass'
check_in "$codex" 'append its ledger skip row (below), and name the skip in the PR body' '§ The Codex pass'
check_in "$codex" 'a `--refusal` row, never a skip row' '§ The Codex pass'

# One recorded run, written into the review cache and never the workspace.
check_in "$codex" '**One recorded run.**' '§ The Codex pass'
check_in "$codex" 'out_file="$dir/codex-adversarial-<n>-gate.out"' '§ The Codex pass'
check_in "$codex" 'record="$dir/codex-adversarial-<n>-gate.json"' '§ The Codex pass'
check_in "$codex" 'status=$?' '§ The Codex pass'
check_in "$codex" '"status": %d' '§ The Codex pass'
check_in "$codex" 'both timestamps and the usage readings' '§ The Codex pass'
check_in "$codex" '**commit nothing while the pass reads**' '§ The Codex pass'
check_in "$codex" 'Both files go in `~/.cache/agent-reviews/<repo>/`, never this workspace' '§ The Codex pass'
check_in "$codex" 'nothing here is cleaned up by hand, `rm` or `rmdir`' '§ The Codex pass'
check_absent_in "$codex" 'rm "$out_file" "$body_file"' '§ The Codex pass'
check_absent_in "$codex" 'rmdir "$(dirname' '§ The Codex pass'
check_absent_in "$codex" 'body_sha256' '§ The Codex pass'

# The gate is fail-closed: an absent answer is never read as a clean pass.
check_in "$codex" '**The gate is fail-closed.**' '§ The Codex pass'
check_in "$codex" 'Absent, unreadable, errored' '§ The Codex pass'
check_in "$codex" 'raced (the two shas differ, so the branch moved while Codex was reading)' '§ The Codex pass'
check_in "$codex" 'is a refusal, not a pass' '§ The Codex pass'
check_in "$codex" 'There is no retry.' '§ The Codex pass'
check_in "$codex" 'either one collected looks exactly like a pass that found nothing' '§ The Codex pass'

# Findings: the k-th `- [severity]` line is codex-gate-<k>, the id the ledger reads.
check_in "$codex" 'the k-th is `codex-gate-<k>`, the id `review_ledger.py` reads it under' '§ The Codex pass'

[ "$fail" -eq 0 ] && echo "PASS implement/codex-wave.test.sh"
exit "$fail"
