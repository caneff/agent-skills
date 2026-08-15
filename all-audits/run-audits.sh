#!/usr/bin/env bash
# Run the guarded audit skills as separate, parallel Claude processes, then
# collect their HTML reports under one folder behind an index.html.
#
# Why a subprocess per audit: the audit skills carry `disable-model-invocation`,
# so an orchestrating agent's Skill tool can't launch them. But `claude -p "/name"`
# is a USER invocation of the slash command, which the guard allows. One process
# per audit => parallelism + context isolation, without loading any skill header
# into a live session.
#
# Usage: run-audits.sh [REPO_PATH]   (defaults to current directory)
set -euo pipefail

REPO="${1:-$PWD}"
REPO="$(cd "$REPO" && pwd)"   # absolute

# ponytail: --dangerously-skip-permissions because these run unattended in the
# background and each needs Read/Grep/Bash/Write to produce its HTML report.
# Drop the flag to run one interactively if you'd rather approve tools by hand.
CLAUDE_FLAGS=(-p --dangerously-skip-permissions)

AUDITS=(
  ponytail-audit
  test-audit
  comment-audit
  thermo-nuclear-code-quality-review
  improve-codebase-architecture
  audit-instructions
)

# Per-run home under a base dir with a self-pruning TTL. Base lives in ~/.cache
# (persistent) not /tmp, which most Linux boxes wipe on reboot — a few-day TTL is
# meaningless if a restart clears it first. Each run gets its own timestamped
# folder, so the skills' fixed report names never collide across runs. TMPDIR is
# pointed at the run dir too, so audit subprocesses that honor ${TMPDIR:-/tmp}
# write their reports into persistent storage instead of raw /tmp.
TTL_DAYS="${AUDITS_TTL_DAYS:-3}"
BASE="${XDG_CACHE_HOME:-$HOME/.cache}/all-audits"
mkdir -p "$BASE"
# TTL: drop run folders older than TTL_DAYS. No cron — each run cleans the past.
find "$BASE" -mindepth 1 -maxdepth 1 -type d -mtime "+$TTL_DAYS" -exec rm -rf {} + 2>/dev/null || true

RUN="$BASE/run-$(date +%Y%m%d-%H%M%S)"
export TMPDIR="$RUN"        # relocate audit reports off fixed /tmp paths
OUT="$RUN/logs"
COLLECTION="$RUN/collection"
mkdir -p "$OUT" "$COLLECTION"
echo "run dir (TTL ${TTL_DAYS}d): $RUN"
echo "collecting under: $COLLECTION"
echo "repo: $REPO"
echo

run_one() {
  local name="$1"
  echo "[$name] starting"
  # The report path the skill prints lands in this log; grep it out afterward.
  claude "${CLAUDE_FLAGS[@]}" "/$name $REPO" >"$OUT/$name.log" 2>&1
  echo "[$name] done"
}

# Test one before fanning out. If the guard rejects a -p slash invocation,
# this fails fast and we don't spawn six.
echo "== smoke test: ponytail-audit =="
run_one ponytail-audit
if grep -qiE 'cannot be used with Skill tool|disable-model-invocation' "$OUT/ponytail-audit.log"; then
  echo "ABORT: -p slash invocation was rejected by the guard. See $OUT/ponytail-audit.log" >&2
  exit 1
fi
echo "smoke test passed; fanning out the rest"
echo

# Fan out the remaining five in parallel.
pids=()
for name in "${AUDITS[@]:1}"; do
  run_one "$name" &
  pids+=("$!")
done
wait "${pids[@]}"

# --- Collect reports ---------------------------------------------------------
# report_link[name] = relative path (name/report.html) into the collection.
declare -A report_link
for name in "${AUDITS[@]}"; do
  report="$(grep -oE '/[^ ]+\.html' "$OUT/$name.log" | head -1 || true)"
  if [ -n "$report" ] && [ -f "$report" ]; then
    cp -r "$(dirname "$report")" "$COLLECTION/$name"
    report_link["$name"]="$name/$(basename "$report")"
  else
    report_link["$name"]=""   # no report produced
  fi
done

# --- Synthesis pass ----------------------------------------------------------
# One more claude -p reads the collected reports and writes a short synthesis for
# the index lede. The audit run itself is dumb bash; this is the only step that
# reads report *content*. Failure is non-fatal — a missing lede beats no index.
report_files=()
for name in "${AUDITS[@]}"; do
  [ -n "${report_link[$name]}" ] && report_files+=("$COLLECTION/${report_link[$name]}")
done
synthesis=""
if [ "${#report_files[@]}" -gt 0 ]; then
  echo "== synthesis pass =="
  synthesis="$(claude "${CLAUDE_FLAGS[@]}" \
    "Read these ${#report_files[@]} audit report HTML files and write a 2-3 sentence synthesis of the repo's overall state for the lede of an index page. Plain prose only — no preamble, no markdown, no headings, no lists. Files: ${report_files[*]}" \
    2>/dev/null || true)"
fi
# Escape for safe HTML injection.
synthesis="$(printf '%s' "$synthesis" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')"

# --- Build index.html (visual-teach styling, matching the reports) -----------
# Reuse a report's own asset tree (base.css + callout + base.js) so the index
# looks like the pages it links to. Copy from the first collected report.
for name in "${AUDITS[@]}"; do
  if [ -d "$COLLECTION/$name/assets" ]; then
    cp -r "$COLLECTION/$name/assets" "$COLLECTION/assets"
    break
  fi
done

index="$COLLECTION/index.html"
{
  cat <<'HEAD'
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All-audits index</title>
<link rel="stylesheet" href="assets/base/base.css">
<link rel="stylesheet" href="assets/components/callout/callout.css">
<script src="assets/base/base.js"></script>
<style>
  main { --vt-measure: 1080px; }
  .audit-table { width:100%; border-collapse:collapse; }
  .audit-table th, .audit-table td { border:1px solid var(--vt-rule); padding:.6rem .8rem; text-align:left; vertical-align:top; }
  .audit-table th { background:var(--vt-soft); font-weight:600; }
  .audit-table tr:nth-child(even) td { background:var(--vt-stripe); }
</style></head><body><main>
HEAD
  printf '<p class="vt-kicker">All-audits sweep</p>\n'
  printf '<h1>%s <span style="color:var(--vt-muted)">· six-audit sweep</span></h1>\n' "$REPO"
  [ -n "$synthesis" ] && printf '<p class="vt-lede">%s</p>\n' "$synthesis"
  echo '<h2>Reports</h2><div class="vt-table-wrap"><table class="audit-table">'
  echo '<thead><tr><th>Audit</th><th>Report</th></tr></thead><tbody>'
  for name in "${AUDITS[@]}"; do
    link="${report_link[$name]}"
    if [ -n "$link" ]; then
      printf '<tr><td>%s</td><td><a href="%s">open report</a></td></tr>\n' "$name" "$link"
    else
      printf '<tr><td>%s</td><td style="color:var(--vt-muted)">no report (see %s.log)</td></tr>\n' "$name" "$name"
    fi
  done
  echo '</tbody></table></div></main></body></html>'
} >"$index"

echo
echo "index: $index"
echo "logs: $OUT"

# Open the index (Linux). Swap for `open` on macOS.
command -v xdg-open >/dev/null && xdg-open "$index" >/dev/null 2>&1 || true
