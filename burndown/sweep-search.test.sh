#!/usr/bin/env bash
# #1248: runs the sweep search exactly as `burndown/SKILL.md` § The sweep and
# `implement/SKILL.md` § The PR write it, against a stub `gh` that applies the
# command's own `--jq` to a fixture. A closed sweep is never "this run's
# sweep": it is off the frontier, so rewriting it loses the new leftovers.
# BASH_SOURCE rather than `git rev-parse --show-toplevel` (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir "$work/bin"
cat >"$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Applies the --jq argument to $FIXTURE, as gh does to its own JSON. Refuses a
# --json list without `state`: real gh would leave .state null and the filter
# would match nothing, which every case expecting a number then reports.
json=""; jqarg=""
while [ $# -gt 0 ]; do
  case "$1" in --json) json="$2" ;; --jq) jqarg="$2" ;; esac
  shift
done
case ",$json," in *,state,*) ;; *) echo "stub gh: --json lacks state: '$json'" >&2; exit 1 ;; esac
exec jq -r "$jqarg" <<<"$FIXTURE"
STUB
chmod +x "$work/bin/gh"

fail=0
run_case() { # label search-script title fixture-states expected
  local label="$1" script="$2" title="$3" rows="$4" want="$5" got fixture
  fixture="$(printf '%s' "$rows" | sed "s|TITLE|$title|g")"
  got="$(FIXTURE="$fixture" PATH="$work/bin:$PATH" bash "$script")" || {
    echo "FAIL: $label: search exited non-zero" >&2; fail=1; return; }
  if [ "$got" != "$want" ]; then
    echo "FAIL: $label: expected '$want', got '$got'" >&2
    fail=1
  fi
}

check_file() { # skill-file title-marker placeholder-title
  local file="$1" marker="$2" title="$3" script="$work/search-$4.sh"
  [ -f "$file" ] || { echo "FAIL: missing $file" >&2; fail=1; return; }
  # The fenced block holding the search, placeholders filled in.
  awk -v m="$marker" '/^```/ { if (inb) { if (blk ~ /in:title/ && index(blk, m)) printf "%s", blk; blk=""; inb=0 } else inb=1; next } inb { blk = blk $0 "\n" }' "$file" \
    | sed -e 's/<run-id>/run-x/g' -e 's/<n>/7/g' -e 's|<owner/name>|o/n|g' >"$script"
  [ -s "$script" ] || { echo "FAIL: $file has no search command" >&2; fail=1; return; }
  local o='{"number":@N@,"title":"TITLE","state":"OPEN"}' c='{"number":@N@,"title":"TITLE","state":"CLOSED"}'
  run_case "$file: open match is the sweep" "$script" "$title" "[${o//@N@/7}]" "7"
  run_case "$file: closed match is not the sweep" "$script" "$title" "[${c//@N@/7}]" ""
  run_case "$file: closed and open: only the open one" "$script" "$title" "[${c//@N@/7},${o//@N@/9}]" "9"
  run_case "$file: fuzzy title match is ignored" "$script" "$title" '[{"number":8,"title":"Sweep: leftovers from burn run-xy","state":"OPEN"}]' ""
}

check_file "$here/SKILL.md" 'burn <run-id>' 'Sweep: leftovers from burn run-x' burn
check_file "$here/../implement/SKILL.md" 'PR #<n>' 'Sweep: leftovers from PR #7' pr

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/sweep-search.test.sh"
else
  exit 1
fi
