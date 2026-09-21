#!/usr/bin/env bash
# Guards #814/#817: `/codex:adversarial-review` (and, in the Codex lane,
# `/codex:review`) carry `disable-model-invocation: true`, so the
# SlashCommand tool never reaches them for a dispatched, unattended session —
# only a human typing the literal command in an interactive session runs
# them. #817 moved the adversarial-review invocation in SKILL.md from the
# worker's round-1 review to the controller's § The merge step 3 (the
# Codex-lane's own invocation in codex-lane.md, run by the worker, is
# unchanged and out of #817's scope); wherever it runs, the caller must
# invoke the plugin's own companion script directly via Bash, resolving its
# installPath from ~/.claude/plugins/installed_plugins.json rather than
# assuming CLAUDE_PLUGIN_ROOT is set outside a slash-command's own execution
# context, and must feed an untrusted ticket body through exactly one
# `-- "$(cat "$body_file")"` substitution — never by interpolating it
# straight into a quoted shell string, the way a naive `"<ticket body
# verbatim>"` placeholder invites (a Codex adversarial-review pass on an
# earlier draft of this fix flagged exactly that, at high severity).
# `--wait`/`--background` are accepted but inert on this path — the
# `AskUserQuestion` gate they dodge lives in the slash command's own
# markdown, which calling the script directly bypasses entirely; the
# script's `handleReviewCommand` never reads either flag.
# This is a prose assertion over the two files, not a behavioral test —
# there is no harness that runs the skills' own prose.
# #877: both of SKILL.md's ticket reads must fetch `--json body,comments`, a
# comment having been invisible to both. What that fetch then renders is
# executed, not grepped, by implement/ticket_comment_render_test.py.
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point
# show-toplevel at that caller's repo instead of this one (#620); resolving
# via BASH_SOURCE sidesteps it entirely rather than relying on the scrub.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
lane="$here/codex-lane.md"

fail=0
check() {
  local file="$1" needle="$2"
  local flat
  flat="$(tr '\n' ' ' <"$file" | tr -s ' ')"
  case "$flat" in
    *"$needle"*) ;;
    *)
      echo "FAIL: $file is missing: $needle" >&2
      fail=1
      ;;
  esac
}
check_count() {
  local file="$1" needle="$2" want="$3"
  local flat got
  flat="$(tr '\n' ' ' <"$file" | tr -s ' ')"
  # grep exits 1 on no match, which `set -e`/`pipefail` would turn into a
  # silent abort of the whole suite instead of the FAIL line below.
  got="$(printf '%s' "$flat" | { grep -o -F -- "$needle" || true; } | wc -l)"
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: $file has $got occurrences of '$needle', want $want" >&2
    fail=1
  fi
}
check_absent() {
  local file="$1" needle="$2" why="$3"
  local flat
  flat="$(tr '\n' ' ' <"$file" | tr -s ' ')"
  case "$flat" in
    *"$needle"*)
      echo "FAIL: $file still has $why: $needle" >&2
      fail=1
      ;;
    *) ;;
  esac
}

# SKILL.md § The merge step 3 (controller, not the worker's § Review):
# direct script invocation, not the disabled slash command. Which section
# the block sits in is codex-fourth-axis-wording.test.sh's rule, not this
# file's — this file only pins the invocation's own shape.
check "$skill" 'disable-model-invocation: true'
check "$skill" "codex@openai-codex"
check "$skill" 'installPath'
check "$skill" 'body_file=<absolute path you wrote the ticket body, comments and appendix to>'
check "$skill" 'codex-companion.mjs" adversarial-review --wait --base origin/<default> -- "$(cat "$body_file")"'
check "$skill" 'the `AskUserQuestion` gate lives there, not in the script'
check "$skill" '`handleReviewCommand` parses `--wait`/`--background` as booleans and'
check_absent "$skill" '"<ticket body verbatim>"' 'the naive, unsafe form'

# #877: two ticket reads, so two comment-carrying fetches, and no read left
# on the comment-less form.
check_count "$skill" '--json body,comments --jq' 2
check_absent "$skill" '--json body --jq .body' 'a comment-less ticket read'

# codex-lane.md § The reviews: same requirement, both commands it names.
check "$lane" 'disable-model-invocation: true'
check "$lane" "codex@openai-codex"
check "$lane" 'installPath'
check "$lane" 'body_file=<absolute path you wrote the ticket body, comments and appendix to>'
check_absent "$lane" 'you wrote the ticket body to>' 'the comment-less body_file wording (#880)'
check_count "$lane" '--json body,comments --jq' 1
check_absent "$lane" 'ticket body **verbatim**' 'a body-only brief (#880)'
check "$lane" 'codex-companion.mjs" review --wait'
check "$lane" 'codex-companion.mjs" adversarial-review --wait --base origin/<default> -- "$(cat "$body_file")"'
check_absent "$lane" '"<ticket body verbatim>"' 'the naive, unsafe form'

# #888: step 3's second pass is conditional on a new input — the head sha
# moving or the ticket text changing (a requirement commented onto the
# ticket between the passes moves the input while the sha sits still, and
# the pass reads `body_file`, not the diff alone), a `fixed` disposition
# with the sha unmoved blocks, and the no-third-run ceiling survives.
check "$skill" 'Note the head sha this pass ran against'
check "$skill" 'The second pass runs only if the head sha moved'
check "$skill" 'The second pass runs only if the head sha moved or the ticket text changed'
check "$skill" 'sha256sum "$body_file"'
check "$skill" 'a fresh render of the ticket hashing differently'
check "$skill" 'If every disposition was `disputed` or `filed`, the sha is unmoved and the ticket hash matches'
check "$skill" 'confirms each disposition is recorded in the Decisions made section and goes to step 4'
check "$skill" 'A disposition that says `fixed` with the sha unmoved is neither case'
check "$skill" 'which a skipped pass still owes'
check_count "$skill" 'there is no third Codex run' 1
check_absent "$skill" 'and then this pass once more on the fixes' 'the unconditional second run'

if [ "$fail" -eq 0 ]; then
  echo "PASS implement/codex-adversarial-invocation.test.sh"
else
  exit 1
fi
