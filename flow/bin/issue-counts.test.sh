#!/usr/bin/env bash
# Characterization test for issue-counts' jq tally. Stubs `gh` with a fixture so
# the label/blockedBy math is checked offline (no network, no real repo).
# Run: bash flow/bin/issue-counts.test.sh
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stub=$(mktemp -d)
trap 'rm -rf "$stub"' EXIT
cat > "$stub/gh" <<'STUB'
#!/usr/bin/env bash
# ignores args, emits a fixed open-issue set:
#  - ready-for-agent, unblocked      -> Ready now
#  - ready-for-agent, blocked        -> NOT ready (blockedBy non-empty)
#  - wayfinder:map                   -> Maps
#  - in-review                       -> In flight
#  - spec + bug                      -> Specs (a frontier label wins; NOT Other)
#  - needs-triage, wayfinder:prototype, bug, [] (unlabeled) -> 🔖 Other (4 issues)
cat <<'JSON'
[
 {"labels":[{"name":"needs-triage"}],"blockedBy":[]},
 {"labels":[{"name":"ready-for-agent"}],"blockedBy":[]},
 {"labels":[{"name":"ready-for-agent"}],"blockedBy":[{"number":1}]},
 {"labels":[{"name":"wayfinder:map"}],"blockedBy":[]},
 {"labels":[{"name":"wayfinder:prototype"}],"blockedBy":[]},
 {"labels":[{"name":"in-review"}],"blockedBy":[]},
 {"labels":[{"name":"spec"},{"name":"bug"}],"blockedBy":[]},
 {"labels":[{"name":"bug"}],"blockedBy":[]},
 {"labels":[],"blockedBy":[]}
]
JSON
STUB
chmod +x "$stub/gh"

got=$(PATH="$stub:$PATH" bash "$here/issue-counts" --status)
want="✅1 🔥0 🗺️1 🚧1 📋1 💤0 🔖4"

if [ "$got" != "$want" ]; then
  echo "FAIL"; echo "  want: $want"; echo "  got:  $got"; exit 1
fi
echo "PASS: $got"
