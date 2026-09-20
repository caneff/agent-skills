#!/usr/bin/env bash
# Guards #892: the run's state is one JSON file per run, and the per-repo
# `~/.cache/burndown/<repo>.progress` log it replaced is retired. Two prose
# assertions no Python harness can make — that nothing in the tree reads or
# writes the retired file, and that `burndown/SKILL.md` points at the reader
# that replaced it. The reader's behaviour is tested in
# burndown/runfile_test.py.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
skill="$here/SKILL.md"
reference="$here/references/run-file.md"

for f in "$skill" "$reference"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

fail=0

# Rule 1: no executable file reads or writes the retired per-repo log. Scoped
# to code — `*.py`, `*.sh` — because prose that *names* the retired file to say
# it is retired is the point, and `docs/research/` records runs that did use
# it. Only code can read one — and this test names it in its own prose, so
# it is excluded too.
if hits="$(git -C "$root" grep -nIE 'cache/burndown/[^ ]*[.]progress' -- '*.py' '*.sh' ':(exclude)burndown/run-file-retirement.test.sh' 2>/dev/null)"; then
  echo "FAIL: code still reaches for the retired per-repo progress file:" >&2
  echo "$hits" >&2
  fail=1
fi

flatten() { tr '\n' ' ' | tr -s ' '; }
skill_text="$(flatten <"$skill")"
reference_text="$(flatten <"$reference")"

check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# Rule 2: the skill names the reader that replaced it, where its file lives,
# and that a worker is addressed by its herdr agent name.
check_in "$skill_text" 'burndown/runfile.py' burndown/SKILL.md
check_in "$skill_text" '~/.cache/burndown/<run-id>.json' burndown/SKILL.md
check_in "$skill_text" 'herdr agent name' burndown/SKILL.md
check_in "$skill_text" 're-announce' burndown/SKILL.md
check_in "$skill_text" 'references/run-file.md' burndown/SKILL.md

# Rule 3: the reference states the retirement itself, so the next reader of
# an old brief knows the file they are looking for is gone on purpose.
check_in "$reference_text" 'retired' references/run-file.md
check_in "$reference_text" 'Nothing reads that file now' references/run-file.md

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/run-file-retirement.test.sh"
else
  exit 1
fi
