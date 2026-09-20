#!/usr/bin/env bash
# Guards #937: the caller derives the diff once, writes it to a file, and
# hands every axis that path — so three opus reviewers read one capture
# instead of each re-running the same `git diff`. The command stays in the
# prompt as provenance and as the fallback: an axis whose file is missing or
# empty re-derives and says so, rather than reviewing nothing.
# Prose assertions over two skill files; there is no harness that runs a
# skill's own prose.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reviewer="$here/../flow/claude/agents/diff-reviewer.md"

for f in "$skill" "$reviewer"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# § 4 scoped to itself: needles this generic must not be satisfied by prose
# in another step. Runs from the step-4 heading to the next `### `.
spawn="$(sed -n '/^###[[:space:]]*4\./,/^###[[:space:]]/{/^###[[:space:]]*4\./d; /^###[[:space:]]/d; p}' "$skill")"
[ -n "$spawn" ] || { echo "FAIL: multi-axis-code-review/SKILL.md has no § 4 step" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }
spawn_text="$(printf '%s\n' "$spawn" | flatten)"
skill_text="$(flatten <"$skill")"
reviewer_text="$(flatten <"$reviewer")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 1: the caller captures the diff to a file once, in the same directory
# as the reports, and fails there on an empty capture rather than inside
# three sub-agents.
check_in "$spawn_text" 'diff-<n>.patch' 'multi-axis-code-review/SKILL.md § 4'
check_in "$spawn_text" 'git -C <worktree> diff <fixed-point>...HEAD >"$dir/diff-' 'multi-axis-code-review/SKILL.md § 4'
check_in "$spawn_text" 'once, by the caller' 'multi-axis-code-review/SKILL.md § 4'

# Rule 2: every axis prompt carries the path AND the command — the path so it
# reads, the command as the provenance record and the fallback. The count is
# the assertion a needle cannot make: an axis bullet that silently drops the
# path fails here even though the other two still carry it.
bullets="$(printf '%s\n' "$spawn" |
  grep -cF 'The captured diff file, the diff command that produced it, and the commit list.' || true)"
if [ "$bullets" -ne 3 ]; then
  echo "FAIL: § 4 hands the captured diff to $bullets axis prompts, not 3" >&2
  fail=1
fi

# Rule 3: the fallback, stated in both homes — the caller's § 4 and the
# standing brief every axis reads.
# "missing or empty" alone is already true of § 4's prose about an empty
# completion notification, so the needle names the diff file itself.
check_in "$spawn_text" 'diff file is missing or empty' 'multi-axis-code-review/SKILL.md § 4'
check_in "$reviewer_text" 'Read the diff from the file the caller names' flow/claude/agents/diff-reviewer.md
check_in "$reviewer_text" 'missing or empty' flow/claude/agents/diff-reviewer.md  # no such prose there yet
check_in "$reviewer_text" 're-derive it with the command' flow/claude/agents/diff-reviewer.md
check_in "$reviewer_text" 'say in your report that you did' flow/claude/agents/diff-reviewer.md
check_in "$reviewer_text" 'git -C <worktree>' flow/claude/agents/diff-reviewer.md

# Rule 4: what #937 ruled out of scope stays put — the axes are Opus and the
# witness check survives. This ticket removes duplicated I/O, not review.
check_in "$reviewer_text" 'model: opus' flow/claude/agents/diff-reviewer.md
check_in "$reviewer_text" 'strip the constraint under test' flow/claude/agents/diff-reviewer.md
check_in "$skill_text" 'Pass `model: opus` to all three' multi-axis-code-review/SKILL.md
witness="$(printf '%s\n' "$spawn" | grep -cF 'strip the constraint under test' || true)"
if [ "$witness" -ne 2 ]; then
  echo "FAIL: § 4 states the witness check in $witness axis briefs, not 2" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/diff-capture.test.sh"
else
  exit 1
fi
