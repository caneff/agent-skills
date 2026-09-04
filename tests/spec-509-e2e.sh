#!/usr/bin/env bash
# End-to-end test for spec #509's cross-cutting invariants across the whole
# skills tree. Run from anywhere; resolves paths off this script's location.
# Prints PASS/FAIL per check and exits nonzero if any check fails.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
fail=0

pass() { printf 'PASS %s\n' "$1"; }
failed() { printf 'FAIL %s\n%s\n' "$1" "$2"; fail=1; }

# 1. No skill invokes its own audit.py/sibling script by relative path —
#    every self-reference to a script in the skill's own dir uses the
#    ~/.agents/skills/... absolute form.
check_1() {
  local hits=""
  for d in */; do
    local name="${d%/}"
    [ -f "$d/SKILL.md" ] || continue
    local m
    # only the skill's own top-level scripts (audit.py/audit.mjs/etc.),
    # invoked without the ~/.agents/skills prefix.
    m=$(grep -n "\`$name/[A-Za-z0-9_.-]*\.\(py\|sh\|mjs\)\`" "$d/SKILL.md" 2>/dev/null \
      | grep -v '~/.agents/skills')
    [ -n "$m" ] && hits="$hits\n$d/SKILL.md:$m"
  done
  if [ -n "$hits" ]; then
    failed "1 no-relative-self-invocation" "$(printf '%b' "$hits")"
  else
    pass "1 no-relative-self-invocation"
  fi
}

# 2. No audit skill restates the harness-owned findings-log/tmpdir/scope
#    block — only all-audits/harness carries the telltale defining phrases.
check_2() {
  local phrases=(
    'For an audit that finds many things, do'
    'One JSON object per line (JSONL)'
    'two artifacts instead'
  )
  local hits=""
  for p in "${phrases[@]}"; do
    local m
    m=$(grep -rl "$p" --include=SKILL.md . 2>/dev/null | grep -v '^\./all-audits/')
    [ -n "$m" ] && hits="$hits\n[$p] -> $m"
  done
  if [ -n "$hits" ]; then
    failed "2 no-harness-block-restated" "$(printf '%b' "$hits")"
  else
    pass "2 no-harness-block-restated"
  fi
}

# 3. uv/ absent; ccstatusline-table absent from skills tree root, present
#    under flow/.
check_3() {
  local msg=""
  [ -d uv ] && msg="$msg uv/ still present at repo root."
  [ -d ccstatusline-table ] && msg="$msg ccstatusline-table/ still present at repo root."
  [ -d flow/ccstatusline-table ] || msg="$msg flow/ccstatusline-table/ missing."
  if [ -n "$msg" ]; then
    failed "3 uv-absent-ccstatusline-relocated" "$msg"
  else
    pass "3 uv-absent-ccstatusline-relocated"
  fi
}

# 4. .extra-skills.json parses and has humanizer, read-the-damn-docs,
#    prompt-master entries each with repo + treeSha.
check_4() {
  local out
  out=$(python3 - <<'PY' 2>&1
import json, sys
try:
    with open(".extra-skills.json") as f:
        data = json.load(f)
except Exception as e:
    print(f"parse error: {e}")
    sys.exit(1)
missing = []
for name in ("humanizer", "read-the-damn-docs", "prompt-master"):
    entry = data.get(name)
    if not entry:
        missing.append(f"{name}: entry missing")
        continue
    if not entry.get("repo"):
        missing.append(f"{name}: repo field missing")
    if not entry.get("treeSha"):
        missing.append(f"{name}: treeSha field missing")
if missing:
    print("\n".join(missing))
    sys.exit(1)
PY
)
  if [ $? -ne 0 ]; then
    failed "4 extra-skills-json" "$out"
  else
    pass "4 extra-skills-json"
  fi
}

# 5. Every reference pointer in python-testing-patterns/SKILL.md resolves
#    to a real file.
check_5() {
  local src=python-testing-patterns/SKILL.md
  local missing=""
  if [ ! -f "$src" ]; then
    failed "5 python-testing-patterns-refs" "$src not found"
    return
  fi
  while IFS= read -r ref; do
    local rel=${ref#\~/.agents/skills/}
    [ -f "$rel" ] || missing="$missing\n$ref -> $rel (not found)"
  done < <(grep -o '`~/\.agents/skills/python-testing-patterns/references/[A-Za-z0-9_.-]*`' "$src" | tr -d '`')
  if [ -n "$missing" ]; then
    failed "5 python-testing-patterns-refs" "$(printf '%b' "$missing")"
  else
    pass "5 python-testing-patterns-refs"
  fi
}

# 6. all-audits/test_run_audits.sh passes (hermetic, no `claude` invoked).
check_6() {
  local out
  out=$(bash all-audits/test_run_audits.sh 2>&1)
  local rc=$?
  if [ $rc -ne 0 ] || printf '%s' "$out" | grep -qi '^FAIL'; then
    failed "6 all-audits-test-suite" "$out"
  else
    pass "6 all-audits-test-suite"
  fi
}

# 7. Statusline segment renders a sample progress file (helper's own
#    --self-check).
check_7() {
  local helper=flow/ccstatusline-table/helpers/burndown-segment.sh
  if [ ! -x "$helper" ] && [ ! -f "$helper" ]; then
    failed "7 statusline-self-check" "$helper not found"
    return
  fi
  local out
  out=$(bash "$helper" --self-check 2>&1)
  local rc=$?
  if [ $rc -ne 0 ]; then
    failed "7 statusline-self-check" "$out"
  else
    pass "7 statusline-self-check"
  fi
}

# 8. #512 AC: no /home/... literal in the statusline wiring snippet, and
#    none in the relocated ccstatusline-table tree. Scoped to that AC only —
#    the rest of the live personal-config mirror (hooks, permissions) is out
#    of scope for #512 and tracked separately.
check_8() {
  local needle="/home/caneff"
  local hits=""
  local m
  m=$(grep -n "$needle" flow/claude/settings.json 2>/dev/null | grep '"statusLine"\|table-statusline.py')
  [ -n "$m" ] && hits="$hits\nflow/claude/settings.json:$m"
  m=$(grep -rn "$needle" flow/ccstatusline-table/ 2>/dev/null)
  [ -n "$m" ] && hits="$hits\n$m"
  if [ -n "$hits" ]; then
    failed "8 no-home-caneff-literal-in-statusline-wiring" "$(printf '%b' "$hits")"
  else
    pass "8 no-home-caneff-literal-in-statusline-wiring"
  fi
}

check_1
check_2
check_3
check_4
check_5
check_6
check_7
check_8

exit "$fail"
