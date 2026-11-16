#!/usr/bin/env bash
# #1881: a repo's merge gate is the command its AGENTS.md `## End-to-end seam`
# section names; no merge path reads `git config land.testcmd` (Chris, 2026-11-14;
# drain/drain_test.py pins it). Only the files that state that fact may name the
# key, and each sentence there that names it must say it is not read. Both
# `git grep` outcomes are checked: exit 1 (no match) is the only clean "none";
# any other non-zero exit fails, never reads as an empty result.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1
# Dated research notes record history and are exempt by name, so a new note
# naming the key as the gate is caught.
allowed='^(flow/claude/WORKFLOW\.md|drain/drain_test\.py|setup-python-repo/SKILL\.md|tests/no-testcmd-gate\.test\.sh|docs/research/2026-09-10-progressive-disclosure-split-report\.md|docs/research/2026-09-10-rule-contradictions\.md|docs/research/2026-10-08-test-smell-gaps\.md|docs/research/2026-10-09-impacted-test-selection\.md)$'
files=$(git grep -l 'land\.testcmd'); rc=$?
if [ "$rc" -gt 1 ]; then echo "FAIL: git grep errored (rc=$rc)" >&2; exit 1; fi
bad=$(printf '%s\n' "$files" | grep -v '^$' | grep -Ev "$allowed" || true)
if [ -n "$bad" ]; then
  echo "FAIL: land.testcmd named outside the files that say no merge reads it:" >&2
  printf '%s\n' "$bad" >&2
  exit 1
fi
# In the two prose files allowed to name it, every sentence naming it must say
# no merge reads it.
python3 -I - flow/claude/WORKFLOW.md setup-python-repo/SKILL.md <<'PY' || exit 1
import re, sys
bad = []
for path in sys.argv[1:]:
    text = re.sub(r"\s+", " ", open(path).read())
    hits = 0
    for sent in re.split(r"(?<=[.!?])\s", text):
        if "land.testcmd" in sent:
            hits += 1
            if "read by no merge path" not in sent and "Nothing reads" not in sent:
                bad.append(f"{path}: {sent[:100]}")
    if hits == 0:
        bad.append(f"{path}: lost its land.testcmd statement")
if bad:
    print("FAIL: land.testcmd sentence does not say no merge reads it:\n" + "\n".join(bad), file=sys.stderr)
    sys.exit(1)
PY
echo "PASS no-testcmd-gate"
