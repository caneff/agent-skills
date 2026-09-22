#!/usr/bin/env bash
# Guards #812/#817: the Codex adversarial-review trial runs from the
# controller's § The merge, at merge time — never from the worker's
# § Review, at review time. This is a prose assertion over
# implement/SKILL.md, not a behavioral test — there is no harness that runs
# the skill's own prose.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
#
# Section-scoped, not whole-file: a check against the whole file (flattened
# or not) only proves a phrase exists *somewhere* — it still passes if the
# Codex block is cut from § The merge and pasted back into the worker's
# § Review verbatim, which is the one thing #817 forbids. So the Codex-block
# checks below run against the § The merge slice alone, and § Review is
# separately asserted clean of it. Within a slice, check() greps a
# whitespace-normalised copy (newlines folded to spaces, runs of spaces
# squeezed to one) so a phrase that happens to sit across a prose line wrap
# still matches — it pins meaning, not where the prose wraps this week; each
# needle is a whole clause, not a wrap-cut fragment, so a partial match can't
# pass on an accident of this week's wrapping either.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"

flatten() { tr '\n' ' ' | tr -s ' '; }

review_section="$(sed -n '/^### Review$/,/^### Before the PR$/p' "$skill" | flatten)"
pr_section="$(sed -n '/^### The PR$/,/^### The merge$/p' "$skill" | flatten)"
merge_section="$(sed -n '/^### The merge$/,/^## Someone else/p' "$skill" | flatten)"
[ -n "$review_section" ] || { echo "FAIL: could not extract § Review from implement/SKILL.md" >&2; exit 1; }
[ -n "$pr_section" ] || { echo "FAIL: could not extract § The PR from implement/SKILL.md" >&2; exit 1; }
[ -n "$merge_section" ] || { echo "FAIL: could not extract § The merge from implement/SKILL.md" >&2; exit 1; }

fail=0
check_in() {
  local section="$1" needle="$2"
  case "$section" in
    *"$needle"*) ;;
    *)
      echo "FAIL: implement/SKILL.md is missing (in the expected section): $needle" >&2
      fail=1
      ;;
  esac
}
check_absent_in() {
  local section="$1" needle="$2" where="$3"
  case "$section" in
    *"$needle"*)
      echo "FAIL: implement/SKILL.md's $where still has: $needle" >&2
      fail=1
      ;;
    *) ;;
  esac
}

# Rule 0: the worker's § Review is the three Claude axes only — no Codex
# pass, no trial-row step, no Codex classes in Decisions made — and it
# points at § The merge instead of restating any of it.
check_absent_in "$review_section" 'Codex adversarial-review pass on the same diff' '§ Review'
check_absent_in "$review_section" 'trial fourth axis' '§ Review'
check_absent_in "$review_section" 'confirmed` (fixed or filed, and no Claude axis raised it), `also found by Claude`, or `disputed`' '§ Review'
check_in "$review_section" 'The Codex adversarial-review trial (#812) runs from the controller, at merge'

# Rule 1: the controller step lives in § The merge, heavy Claude-lane PRs
# only, with an explicit skip for everything else.
check_in "$merge_section" 'Codex adversarial-review pass (#812 trial) — heavy Claude-lane PRs'
check_in "$merge_section" "a Codex-lane build's own review step is \`codex-lane.md\`'s, unchanged"

# Rule 2: never blocks a build.
check_in "$merge_section" 'Run `codex login status` first'
check_in "$merge_section" 'comment `Codex pass skipped: <why>` on the PR'
check_in "$merge_section" 'a skip adds no trial row'

# Rule 3: raw output is a PR comment, posted before acting on it, and the
# file it is posted from survives the workspace — #942 moved it out of
# `.scratch/` into the review cache (Rules 9-11 below carry why).
check_in "$merge_section" 'Post it from the cache directory'
check_in "$merge_section" '`gh pr comment <pr> --repo <owner/name> --body-file "$out_file"`'

# Rule 4: findings hold the merge; the worker disposes of them and records
# the dispositions itself; the CLEAN check reruns; whatever a later run
# finds still gets a disposition — a finding outside the adjacent-fix rule
# (#1028) the controller disposes of directly rather than merging it
# unrecorded.
check_in "$merge_section" 'No material findings → go to step 4. Findings → hold the merge'
check_in "$merge_section" 'send the worker the findings and the comment URL'
check_in "$merge_section" "adds each disposition to the PR body's Decisions made section"
check_in "$merge_section" 'Re-run step 2 (not-draft, CLEAN'
check_in "$merge_section" 'The controller disposes of every other second-pass finding in the PR body itself'

# Rule 5: the controller classifies and appends the trial row once the
# merge lands, including on the ready-for-human path (which hands the
# merge itself to Chris but still owes the row).
check_in "$merge_section" 'append one row to `docs/research/2026-09-14-codex-review-trial.md`'
check_in "$merge_section" 'This row is an auto-ship commit on `<default>` (docs/research is not code)'
check_in "$merge_section" "once Chris reports the PR merged"
check_in "$merge_section" "doesn't stop with the hand-off"

# Rule 6: the controller counts rows and brings Chris the table after five.
check_in "$merge_section" "After the controller's own row brings the count to five, bring"
check_in "$merge_section" 'Chris the table and a keep/drop recommendation'
check_absent_in "$review_section" '"codex trial complete" in "PR up"' '§ Review'

# Rule 7 (a controller Codex pass on PR #818 found this): the PR body must
# carry every round-1 finding with its disposition, fixed ones included —
# not just disputed/filed — or the controller's classification can't tell a
# fixed Claude finding from a Codex-only one and misclassifies it.
check_in "$review_section" 'the PR body lists **every** round-1 finding with its'
check_in "$review_section" 'fixed, with the fixing commit'
check_in "$pr_section" 'every round-1 finding, each with its disposition'

# Rule 8 (a controller Codex pass on PR #818 found this): the raw output
# needs a bound, captured file — not bare stdout — or there is nothing to
# post as the PR comment.
check_in "$merge_section" 'out_file="$dir/codex-adversarial-<n>-$phase.out"'
check_in "$merge_section" 'adversarial-review --wait --base origin/<default> -- "$(cat "$body_file")" >"$out_file" 2>&1'
check_in "$merge_section" 'gh pr comment <pr> --repo <owner/name> --body-file "$out_file"`, before acting on it'
check_in "$merge_section" 'If `gh pr comment` fails, stop before merging'

# Rules 9-11 were the `.scratch/` cleanup: the pass used to write its output
# into the PR's workspace, so it had to `rm` the two files and `rmdir` the
# directory its own `mkdir -p` created, bound to the file's directory rather
# than a bare `.scratch` relative to the controller's cwd, and report an
# rmdir failure instead of silencing it — merge-cleanup refuses ignored
# `.scratch/` content without `--discard`, so anything left there stalled it
# on every Codex pass (#835, PRs #839 and #840). #942 removed the hazard
# instead of guarding it: the files live in `~/.cache/agent-reviews/<repo>/`,
# outside the workspace, where the worker's own § Before the PR step cannot
# delete an in-flight pass's output and the directory's 14-day prune
# collects them. So the rule is now that the pass writes nothing into the
# workspace and cleans nothing up by hand — and no `rm`/`rmdir` may come
# back, because a cleanup aimed at the cache directory would delete the one
# copy of the verdict and take the Claude axes' reports with it.
check_in "$merge_section" '`~/.cache/agent-reviews/<repo>/`, never this workspace'
check_in "$merge_section" 'nothing here is cleaned up by hand, `rm` or `rmdir`, in any phase'
check_absent_in "$merge_section" 'rm "$out_file" "$body_file"' '§ The merge'
check_absent_in "$merge_section" 'rmdir "$(dirname' '§ The merge'
check_absent_in "$merge_section" '.scratch/codex-adversarial' '§ The merge'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-fourth-axis-wording.test.sh"
else
  exit 1
fi
