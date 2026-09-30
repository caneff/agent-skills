#!/usr/bin/env bash
# #1248: runs the sweep search exactly as `burndown/SKILL.md` § The sweep
# writes it, against a stub `gh` that applies the command's own `--jq` to a
# fixture. A closed sweep already landed its items, so it must never be the
# one "this run's sweep" names: a closed match rewrote a ticket that never
# reaches the frontier, and the new leftovers were lost.
# BASH_SOURCE rather than `git rev-parse --show-toplevel` (#620).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
[ -f "$skill" ] || { echo "FAIL: missing $skill" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# The fenced block holding the search, placeholders filled in.
awk '/^```/ { if (inb) { if (blk ~ /in:title/ && blk ~ /burn <run-id>/) printf "%s", blk; blk=""; inb=0 } else inb=1; next } inb { blk = blk $0 "\n" }' "$skill" \
  | sed -e 's/<run-id>/run-x/g' -e 's|<owner/name>|o/n|g' >"$work/search.sh"
[ -s "$work/search.sh" ] || { echo "FAIL: burndown/SKILL.md § The sweep has no search command" >&2; exit 1; }

mkdir "$work/bin"
cat >"$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Applies the --jq argument to $FIXTURE, as gh does to its own JSON.
while [ $# -gt 0 ]; do
  [ "$1" = "--jq" ] && { jq -r "$2" <<<"$FIXTURE"; exit 0; }
  shift
done
exit 1
STUB
chmod +x "$work/bin/gh"

fail=0
run_case() { # name fixture expected-output
  local got
  got="$(FIXTURE="$2" PATH="$work/bin:$PATH" bash "$work/search.sh")"
  if [ "$got" != "$3" ]; then
    echo "FAIL: $1: expected '$3', got '$got'" >&2
    fail=1
  fi
}

t='"title":"Sweep: leftovers from burn run-x"'
run_case "open match is this run's sweep" "[{\"number\":7,$t,\"state\":\"OPEN\"}]" "7"
run_case "closed match is not this run's sweep" "[{\"number\":7,$t,\"state\":\"CLOSED\"}]" ""
run_case "closed and open: only the open one" "[{\"number\":7,$t,\"state\":\"CLOSED\"},{\"number\":9,$t,\"state\":\"OPEN\"}]" "9"
run_case "fuzzy title match is ignored" '[{"number":8,"title":"Sweep: leftovers from burn run-xy","state":"OPEN"}]' ""

if [ "$fail" -eq 0 ]; then
  echo "PASS burndown/sweep-search.test.sh"
else
  exit 1
fi
